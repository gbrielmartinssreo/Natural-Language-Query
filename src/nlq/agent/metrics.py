"""Instrumentação de desempenho das execuções do agente.

Coleta, sem registrar conteúdo sensível das planilhas:

- duração de cada chamada ao modelo;
- tokens de entrada/saída quando o provider informar;
- quantidade de chamadas ao modelo e de ferramentas;
- caracteres retornados por ferramenta;
- tempo total do turno e tamanho do histórico.

Uso: passar uma instância em ``config["callbacks"]`` e chamar
``resumo()``/``imprimir()`` ao fim do turno.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


def _uso_tokens(
    response: Any,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Extrai (entrada, saida, total, cache_read) de um ``LLMResult``.

    ``cache_read`` é quantos tokens de entrada vieram de cache de prompt.
    """
    entrada = saida = total = cache_read = None

    llm_output = getattr(response, "llm_output", None) or {}
    uso = llm_output.get("token_usage") or llm_output.get("usage") or {}

    if uso:
        entrada = uso.get("prompt_tokens") or uso.get("input_tokens")
        saida = uso.get("completion_tokens") or uso.get("output_tokens")
        total = uso.get("total_tokens")
        detalhes = uso.get("input_token_details") or {}
        cache_read = detalhes.get("cache_read")

    if total is None:
        for geracoes in getattr(response, "generations", []) or []:
            for geracao in geracoes:
                mensagem = getattr(geracao, "message", None)
                meta = (
                    getattr(mensagem, "usage_metadata", None)
                    if mensagem is not None
                    else None
                )

                if meta:
                    entrada = meta.get("input_tokens", entrada)
                    saida = meta.get("output_tokens", saida)
                    total = meta.get("total_tokens", total)
                    detalhes = meta.get("input_token_details") or {}
                    cache_read = detalhes.get("cache_read", cache_read)

    return entrada, saida, total, cache_read


class PerfCallbackHandler(BaseCallbackHandler):
    """Mede chamadas ao modelo e ferramentas durante um turno."""

    def __init__(self) -> None:
        super().__init__()
        self.llm_calls: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self._llm_start: dict[Any, float] = {}
        self._tool_start: dict[Any, float] = {}
        self._tool_name: dict[Any, str] = {}

    # -- modelo -------------------------------------------------------
    def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        self._llm_start[kwargs.get("run_id")] = perf_counter()

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        # Modelos de chat disparam este gancho, e não on_llm_start.
        self._llm_start[kwargs.get("run_id")] = perf_counter()

    def on_llm_end(self, response, **kwargs) -> None:
        run_id = kwargs.get("run_id")
        inicio = self._llm_start.pop(run_id, None)
        entrada, saida, total, cache_read = _uso_tokens(response)
        self.llm_calls.append({
            "duracao": perf_counter() - inicio if inicio is not None else None,
            "tokens_entrada": entrada,
            "tokens_saida": saida,
            "tokens_total": total,
            "cache_read": cache_read,
        })

    # -- ferramentas --------------------------------------------------
    def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        run_id = kwargs.get("run_id")
        self._tool_start[run_id] = perf_counter()
        self._tool_name[run_id] = (
            (serialized or {}).get("name") or kwargs.get("name") or "tool"
        )

    def on_tool_end(self, output, **kwargs) -> None:
        run_id = kwargs.get("run_id")
        inicio = self._tool_start.pop(run_id, None)
        conteudo = (
            output
            if isinstance(output, str)
            else str(getattr(output, "content", output))
        )
        self.tool_calls.append({
            "nome": self._tool_name.pop(run_id, "tool"),
            "duracao": perf_counter() - inicio if inicio is not None else None,
            "chars": len(conteudo),
        })

    # -- resumo -------------------------------------------------------
    def resumo(self) -> dict[str, Any]:
        duracoes = [c["duracao"] for c in self.llm_calls if c["duracao"]]
        entrada = sum(
            c["tokens_entrada"] or 0 for c in self.llm_calls
        )
        saida = sum(c["tokens_saida"] or 0 for c in self.llm_calls)
        total = sum(c["tokens_total"] or 0 for c in self.llm_calls)
        cache_read = sum(c.get("cache_read") or 0 for c in self.llm_calls)

        return {
            "llm_chamadas": len(self.llm_calls),
            "llm_tempo_total": round(sum(duracoes), 4),
            "llm_duracao_por_chamada": [round(d, 4) for d in duracoes],
            "tokens_entrada": entrada or None,
            "tokens_saida": saida or None,
            "tokens_total": total or None,
            "cache_read": cache_read or None,
            "llm_detalhe": [
                {
                    "entrada": c["tokens_entrada"],
                    "saida": c["tokens_saida"],
                    "cache_read": c.get("cache_read"),
                    "duracao": (
                        round(c["duracao"], 4) if c["duracao"] else None
                    ),
                }
                for c in self.llm_calls
            ],
            "tool_chamadas": len(self.tool_calls),
            "tool_chars_total": sum(c["chars"] for c in self.tool_calls),
            "tool_detalhe": [
                {
                    "nome": c["nome"],
                    "chars": c["chars"],
                    "duracao": (
                        round(c["duracao"], 4) if c["duracao"] else None
                    ),
                }
                for c in self.tool_calls
            ],
        }

    def imprimir(self) -> None:
        r = self.resumo()
        tokens = (
            f"entrada={r['tokens_entrada']} saida={r['tokens_saida']} "
            f"total={r['tokens_total']} cache_read={r['cache_read']}"
            if r["tokens_total"] is not None
            else "não informados pelo provider"
        )
        print(
            f"[PERF] llm chamadas={r['llm_chamadas']} "
            f"tempo={r['llm_tempo_total']}s tokens={tokens}",
            flush=True,
        )

        for i, chamada in enumerate(r["llm_detalhe"], start=1):
            print(
                f"[PERF]   llm#{i} entrada={chamada['entrada']} "
                f"saida={chamada['saida']} "
                f"cache_read={chamada['cache_read']} "
                f"tempo={chamada['duracao']}s",
                flush=True,
            )

        print(
            f"[PERF] tools chamadas={r['tool_chamadas']} "
            f"chars={r['tool_chars_total']}",
            flush=True,
        )

        for item in r["tool_detalhe"]:
            print(
                f"[PERF]   tool={item['nome']} chars={item['chars']} "
                f"tempo={item['duracao']}s",
                flush=True,
            )
