"""
Testes do cancelamento cooperativo do NLQ.

Executar:

    .venv/bin/python -m unittest discover -s tests -v

Não fazem chamadas de rede: o provider é forçado para o Groq com uma
chave fictícia, então `check_openrouter_key()` nem é chamado.
"""

import os

os.environ.setdefault("API_SELECT", "groq")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import threading
import time
import unittest
from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.errors import GraphDrained
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import RunControl

import nlq.api as api


class _FakeAgent:
    """Agente falso que conta as etapas e respeita o drain."""

    def __init__(self, passos=5, delay=0.0, erro=None):
        self.passos = passos
        self.delay = delay
        self.erro = erro
        self.executados = 0
        self.recebeu_control = False

    def stream(self, entrada, config=None, stream_mode=None, control=None):
        self.recebeu_control = control is not None

        for i in range(self.passos):
            if control is not None and control.drain_requested:
                raise GraphDrained("teste")

            if self.delay:
                time.sleep(self.delay)

            self.executados += 1
            yield {"messages": [f"passo-{i}"]}

        if self.erro is not None:
            raise self.erro


class TestExecutarAgente(unittest.TestCase):
    def test_fluxo_normal_publica_fim(self):
        agente = _FakeAgent(passos=3)
        eventos = []

        api._executar_agente(
            agente,
            {},
            {},
            eventos.append,
            threading.Event(),
            RunControl(),
        )

        tipos = [tipo for tipo, _ in eventos]

        self.assertTrue(agente.recebeu_control)
        self.assertEqual(agente.executados, 3)
        self.assertEqual(eventos[-1][0], "fim")
        self.assertIn("status", tipos)

    def test_cancelamento_interrompe_e_nao_publica_fim(self):
        agente = _FakeAgent(passos=100000, delay=0.001)
        cancelado = threading.Event()
        control = RunControl()
        eventos = []

        thread = threading.Thread(
            target=api._executar_agente,
            args=(agente, {}, {}, eventos.append, cancelado, control),
        )
        thread.start()

        time.sleep(0.05)
        cancelado.set()
        control.request_drain("client_disconnect")

        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertLess(agente.executados, 100000)
        self.assertNotIn("fim", [tipo for tipo, _ in eventos])

    def test_excecao_publica_erro(self):
        agente = _FakeAgent(passos=1, erro=RuntimeError("boom"))
        eventos = []

        with self.assertLogs("nlq.api", level="ERROR"):
            api._executar_agente(
                agente,
                {},
                {},
                eventos.append,
                threading.Event(),
                RunControl(),
            )

        self.assertIn("erro", [tipo for tipo, _ in eventos])


class _FakeStreamAgent:
    """Agente falso que reproduz itens no formato do modo múltiplo."""

    def __init__(self, itens):
        self.itens = itens
        self.recebeu_stream_mode = None
        self.recebeu_control = False

    def stream(self, entrada, config=None, stream_mode=None, control=None):
        self.recebeu_stream_mode = stream_mode
        self.recebeu_control = control is not None

        for item in self.itens:
            if control is not None and control.drain_requested:
                raise GraphDrained("teste")

            yield item


def _chunk(content, tool_call_chunks=None):
    """Chunk de IA compatível com o modo "messages"."""
    return AIMessageChunk(
        content=content,
        tool_call_chunks=tool_call_chunks or [],
    )


class TestStreamingTokens(unittest.TestCase):
    def test_streaming_publica_tokens_coalescidos_e_fim(self):
        agente = _FakeStreamAgent([
            ("messages", (_chunk("Olá "), {})),
            ("messages", (_chunk("mundo"), {})),
            (
                "messages",
                (
                    _chunk(
                        "",
                        tool_call_chunks=[
                            {"name": "x", "args": "", "id": "1", "index": 0}
                        ],
                    ),
                    {},
                ),
            ),
            ("values", {"messages": []}),
        ])

        eventos = []

        api._executar_agente(
            agente,
            {},
            {},
            eventos.append,
            threading.Event(),
            RunControl(),
        )

        self.assertEqual(
            agente.recebeu_stream_mode,
            ["messages", "values"],
        )

        texto = "".join(
            payload for tipo, payload in eventos if tipo == "token"
        )

        self.assertEqual(texto, "Olá mundo")
        self.assertEqual(eventos[-1][0], "fim")

    def test_cancelamento_nao_publica_tokens_tardios(self):
        agente = _FakeStreamAgent([
            ("messages", (_chunk("a"), {})),
            ("messages", (_chunk("b"), {})),
        ])

        cancelado = threading.Event()
        eventos = []

        def publicar(item):
            eventos.append(item)

            if item[0] == "token":
                cancelado.set()

        api._executar_agente(
            agente,
            {},
            {},
            publicar,
            cancelado,
            RunControl(),
        )

        self.assertNotIn("fim", [tipo for tipo, _ in eventos])


class _State(TypedDict):
    passos: Annotated[int, add]


class TestDrainLangGraph(unittest.TestCase):
    """Confirma que o mecanismo nativo do LangGraph para no superstep."""

    def test_drain_real_para_cedo_e_levanta_graphdrained(self):
        def no(state):
            time.sleep(0.02)
            return {"passos": 1}

        def continuar(state):
            return "no" if state["passos"] < 100 else END

        builder = StateGraph(_State)
        builder.add_node("no", no)
        builder.add_edge(START, "no")
        builder.add_conditional_edges(
            "no",
            continuar,
            {"no": "no", END: END},
        )
        grafo = builder.compile()

        control = RunControl()
        eventos = []

        threading.Thread(
            target=lambda: (
                time.sleep(0.1),
                control.request_drain("teste"),
            )
        ).start()

        with self.assertRaises(GraphDrained):
            for estado in grafo.stream(
                {"passos": 0},
                stream_mode="values",
                control=control,
            ):
                eventos.append(estado)

        self.assertLess(eventos[-1]["passos"], 100)


class TestLimparConversa(unittest.TestCase):
    def test_thread_ativa_retorna_409(self):
        with api._consultas_lock:
            api._consultas_ativas.add("thread-x")

        try:
            resposta = api.clear_chat(
                api.LimparConversaRequest(thread_id="thread-x")
            )
            self.assertEqual(resposta.status_code, 409)
        finally:
            with api._consultas_lock:
                api._consultas_ativas.discard("thread-x")

    def test_thread_inativa_apaga(self):
        chamadas = []
        original = api.checkpointer.delete_thread
        api.checkpointer.delete_thread = lambda tid: chamadas.append(tid)

        try:
            resposta = api.clear_chat(
                api.LimparConversaRequest(thread_id="livre")
            )
        finally:
            api.checkpointer.delete_thread = original

        self.assertEqual(resposta, {"status": "ok"})
        self.assertEqual(chamadas, ["livre"])


class TestHelpers(unittest.TestCase):
    def test_linha_ndjson(self):
        self.assertEqual(
            api._linha({"type": "ping", "status": "x"}),
            '{"type": "ping", "status": "x"}\n',
        )

    def test_status_do_estado(self):
        self.assertEqual(api._status_do_estado(None), "processando")
        self.assertEqual(
            api._status_do_estado({"messages": []}),
            "processando",
        )

        classe_tool_call = type(
            "M",
            (),
            {"content": "", "tool_calls": [{"name": "x"}]},
        )

        self.assertEqual(
            api._status_do_estado({"messages": [classe_tool_call()]}),
            "executando ferramenta",
        )

        self.assertEqual(
            api._status_do_estado(
                {
                    "messages": [
                        ToolMessage(content="r", tool_call_id="1")
                    ]
                }
            ),
            "executando ferramenta",
        )

        classe_texto = type("N", (), {"content": "oi"})

        self.assertEqual(
            api._status_do_estado({"messages": [classe_texto()]}),
            "consultando modelo",
        )

    def test_separar_evento(self):
        self.assertEqual(
            api._separar_evento(("messages", ("c", {}))),
            ("messages", ("c", {})),
        )

        estado = {"messages": []}

        self.assertEqual(
            api._separar_evento(estado),
            ("values", estado),
        )

    def test_token_do_chunk(self):
        self.assertEqual(
            api._token_do_chunk((_chunk("abc"), {})),
            "abc",
        )

        self.assertEqual(
            api._token_do_chunk(
                (
                    _chunk(
                        "abc",
                        tool_call_chunks=[
                            {"name": "x", "args": "", "id": "1", "index": 0}
                        ],
                    ),
                    {},
                )
            ),
            "",
        )

        self.assertEqual(
            api._token_do_chunk(
                (_chunk([{"type": "text", "text": "olá "},
                          {"type": "text", "text": "mundo"}]), {})
            ),
            "olá mundo",
        )

        # Mensagem de ferramenta não é transmitida como token.
        self.assertEqual(
            api._token_do_chunk(
                (ToolMessage(content="resultado", tool_call_id="1"), {})
            ),
            "",
        )

        # Payload fora do formato esperado não quebra.
        self.assertEqual(api._token_do_chunk("solto"), "")

    def test_texto_final(self):
        self.assertEqual(
            api._texto_final(type("M", (), {"content": "a"})()),
            "a",
        )
        self.assertEqual(
            api._texto_final(
                type(
                    "L",
                    (),
                    {
                        "content": [
                            {"type": "text", "text": "olá "},
                            {"type": "text", "text": "mundo"},
                        ]
                    },
                )()
            ),
            "olá mundo",
        )

    def test_ultima_planilha(self):
        class TC:
            def __init__(self, name, args):
                self.name = name
                self.args = args

        class M:
            def __init__(self, tcs):
                self.tool_calls = tcs

        resultado = {
            "messages": [
                M([TC("create_json", {"name": "dados", "ext": "csv"})])
            ]
        }

        self.assertEqual(
            api._ultima_planilha(resultado),
            {"nome": "dados", "ext": "csv"},
        )


if __name__ == "__main__":
    unittest.main()
