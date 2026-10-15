"""Testes da instrumentação de desempenho do agente."""

from types import SimpleNamespace

from nlq.agent.metrics import PerfCallbackHandler


class _Resposta:
    def __init__(self, uso=None, geracoes=None):
        self.llm_output = {"token_usage": uso} if uso else {}
        self.generations = geracoes or []


def test_registra_chamada_de_chat_model_com_tokens():
    perf = PerfCallbackHandler()
    perf.on_chat_model_start({}, [[]], run_id="r1")
    perf.on_llm_end(
        _Resposta(uso={"prompt_tokens": 100, "completion_tokens": 20,
                       "total_tokens": 120}),
        run_id="r1",
    )
    resumo = perf.resumo()
    assert resumo["llm_chamadas"] == 1
    assert resumo["tokens_entrada"] == 100
    assert resumo["tokens_saida"] == 20
    assert resumo["tokens_total"] == 120
    assert resumo["llm_duracao_por_chamada"][0] >= 0


def test_tokens_via_usage_metadata_da_mensagem():
    perf = PerfCallbackHandler()
    mensagem = SimpleNamespace(
        usage_metadata={"input_tokens": 7, "output_tokens": 3,
                        "total_tokens": 10}
    )
    perf.on_llm_start({}, ["oi"], run_id="r2")
    perf.on_llm_end(
        _Resposta(geracoes=[[SimpleNamespace(message=mensagem)]]),
        run_id="r2",
    )
    resumo = perf.resumo()
    assert resumo["tokens_total"] == 10


def test_registra_ferramenta_e_chars():
    perf = PerfCallbackHandler()
    perf.on_tool_start({"name": "consultar_dados"}, "{}", run_id="t1")
    perf.on_tool_end("a" * 42, run_id="t1")
    resumo = perf.resumo()
    assert resumo["tool_chamadas"] == 1
    assert resumo["tool_chars_total"] == 42
    assert resumo["tool_detalhe"][0]["nome"] == "consultar_dados"


def test_resumo_sem_tokens_nao_inventa_zero():
    perf = PerfCallbackHandler()
    perf.on_llm_start({}, ["oi"], run_id="r3")
    perf.on_llm_end(_Resposta(), run_id="r3")
    resumo = perf.resumo()
    assert resumo["tokens_total"] is None
    assert resumo["llm_chamadas"] == 1
