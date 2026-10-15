"""Poda de contexto (ContextEditingMiddleware) do agente NLQ.

Cobertura:
- ClearToolUsesEdit: limpa ToolMessages antigos acima do gatilho,
  preservando os `keep` mais recentes e mensagens de conversa.
- ContextEditingMiddleware.wrap_model_call: envia versão editada ao
  handler SEM mutar a lista original (integridade do checkpointer).

Execução: .venv/Scripts/python -m unittest discover -s tests -v
"""

import unittest

from langchain.agents.middleware.context_editing import (
    DEFAULT_TOOL_PLACEHOLDER,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _falso_contador(messages):
    """Contagem por número de mensagens: determinística e barata."""
    return len(messages)


def _conversa_com_tools(n_tools: int, chars_por_resultado: int = 500):
    """Histórico sintético: 1 pergunta + n_tools pares (call/result) + final."""
    mensagens = [HumanMessage(content="quantos registros tem a planilha?")]

    for i in range(n_tools):
        call_id = f"call_{i}"
        mensagens.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "consultar_dados",
                        "args": {"name": "dados", "ext": "csv", "operacao": "contar"},
                        "id": call_id,
                        "type": "tool_call",
                    }
                ],
            )
        )
        mensagens.append(
            ToolMessage(
                content=f"resultado {i} " * chars_por_resultado,
                name="consultar_dados",
                tool_call_id=call_id,
            )
        )

    mensagens.append(AIMessage(content="A planilha tem 42 registros."))
    return mensagens


class TestClearToolUsesEdit(unittest.TestCase):
    def test_abaixo_do_gatilho_nao_poda(self):
        mensagens = _conversa_com_tools(4)
        edit = ClearToolUsesEdit(trigger=10_000, keep=1)

        edit.apply(mensagens, count_tokens=_falso_contador)

        tools = [m for m in mensagens if isinstance(m, ToolMessage)]
        self.assertEqual(len(tools), 4)
        for tool in tools:
            self.assertNotEqual(tool.content, DEFAULT_TOOL_PLACEHOLDER)

    def test_acima_do_gatilho_poda_antigos_e_preserva_recentes(self):
        mensagens = _conversa_com_tools(6)
        # trigger=1: sempre dispara (6 mensagens de tool + outras > 1).
        edit = ClearToolUsesEdit(trigger=1, keep=2)

        edit.apply(mensagens, count_tokens=_falso_contador)

        tools = [m for m in mensagens if isinstance(m, ToolMessage)]
        self.assertEqual(len(tools), 6)

        podados = [t for t in tools if t.content == DEFAULT_TOOL_PLACEHOLDER]
        preservados = [t for t in tools if t.content != DEFAULT_TOOL_PLACEHOLDER]

        # Os 4 antigos são limpos; os 2 mais recentes ficam intactos.
        self.assertEqual(len(podados), 4)
        self.assertEqual(len(preservados), 2)
        self.assertIn("resultado 5", preservados[-1].content)
        self.assertIn("resultado 4", preservados[0].content)

    def test_mensagens_de_conversa_nunca_sao_podadas(self):
        mensagens = _conversa_com_tools(3)
        edit = ClearToolUsesEdit(trigger=1, keep=0)

        edit.apply(mensagens, count_tokens=_falso_contador)

        humano = mensagens[0]
        self.assertIsInstance(humano, HumanMessage)
        self.assertEqual(humano.content, "quantos registros tem a planilha?")

        final = mensagens[-1]
        self.assertIsInstance(final, AIMessage)
        self.assertEqual(final.content, "A planilha tem 42 registros.")

    def test_marcacao_de_podado_no_metadata(self):
        mensagens = _conversa_com_tools(2)
        edit = ClearToolUsesEdit(trigger=1, keep=0)

        edit.apply(mensagens, count_tokens=_falso_contador)

        tools = [m for m in mensagens if isinstance(m, ToolMessage)]
        for tool in tools:
            self.assertTrue(
                tool.response_metadata.get("context_editing", {}).get("cleared")
            )


class _ModeloFalso:
    """Substituto mínimo de BaseChatModel para ModelRequest."""

    def get_num_tokens_from_messages(self, messages, tools=None):
        return len(messages)


class TestContextEditingMiddleware(unittest.TestCase):
    def test_wrap_envia_editado_sem_mutar_original(self):
        mensagens = _conversa_com_tools(4)
        original = list(mensagens)

        middleware = ContextEditingMiddleware(
            edits=[ClearToolUsesEdit(trigger=1, keep=1)]
        )

        from langchain.agents.middleware.types import ModelRequest

        request = ModelRequest(
            model=_ModeloFalso(),
            messages=mensagens,
        )

        recebido = {}

        def handler(req):
            recebido["messages"] = list(req.messages)
            from langchain.agents.middleware.types import ModelResponse

            return ModelResponse(result=[AIMessage(content="ok")])

        middleware.wrap_model_call(request, handler)

        # O handler recebe a versão editada.
        tools_recebidos = [
            m for m in recebido["messages"] if isinstance(m, ToolMessage)
        ]
        podados = [
            t
            for t in tools_recebidos
            if t.content == DEFAULT_TOOL_PLACEHOLDER
        ]
        self.assertEqual(len(podados), 3)

        # A lista original (estado/checkpointer) permanece intacta.
        tools_original = [
            m for m in mensagens if isinstance(m, ToolMessage)
        ]
        for tool in tools_original:
            self.assertNotEqual(tool.content, DEFAULT_TOOL_PLACEHOLDER)

        # E a estrutura da lista original não foi alterada em profundidade
        # das referências: cada posição corresponde ao mesmo tipo.
        self.assertEqual(len(mensagens), len(original))
        for atual, antes in zip(mensagens, original):
            self.assertIsInstance(atual, type(antes))


if __name__ == "__main__":
    unittest.main()
