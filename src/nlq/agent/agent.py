from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
from langchain.agents.middleware.context_editing import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
)
from langchain_core.messages import ToolMessage
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver

import json
import os
import threading
import time
import uuid

import requests

from nlq.paths import load_env, prompts_dir, skills_dir
from nlq.tools.extract import create_json
from nlq.tools.dev_master import goat
from nlq.tools.listar_planilhas import lista_arquivos
from nlq.tools.schema_info import consultar_schema
from nlq.tools.retrieval import buscar_semantico
from nlq.tools.consultar_dados import consultar_dados


load_env()


def load_prompt(name: str) -> str:
    return (prompts_dir() / name).read_text(encoding="utf-8")


def check_openrouter_key() -> bool:
    key = os.getenv("OPENROUTER_API_KEY")

    if not key:
        return False

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={
                "Authorization": f"Bearer {key}",
            },
            timeout=5,
        )

        return response.status_code == 200

    except requests.RequestException:
        return False


class CacheDeChamadas(AgentMiddleware):
    """Evita loops de consultas idênticas repetidas pelo modelo.

    Quando o modelo repete a mesma ferramenta com os mesmos argumentos,
    devolve o resultado já obtido (em vez de executar de novo) com um
    aviso para concluir a resposta.
    """

    _TTL_S = 300.0
    _MAX = 256

    def __init__(self) -> None:
        super().__init__()
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _chave(tool_call: dict) -> str:
        nome = tool_call.get("name", "")
        args = tool_call.get("args") or {}
        return nome + "\x00" + json.dumps(
            args, sort_keys=True, ensure_ascii=False, default=str
        )

    def wrap_tool_call(self, request, handler):
        try:
            chave = self._chave(request.tool_call)
        except Exception:
            return handler(request)

        agora = time.time()

        with self._lock:
            for k, (_, t) in list(self._cache.items()):
                if agora - t > self._TTL_S:
                    del self._cache[k]

            item = self._cache.get(chave)

        if item is not None:
            conteudo, _ = item

            return ToolMessage(
                content=(
                    f"{conteudo}\n\n"
                    "[REPETIDO] Esta chamada já foi executada nesta conversa "
                    "e não trouxe dados novos. Não repita consultas: use o "
                    "resultado acima e conclua a resposta."
                ),
                name=request.tool_call.get("name", "ferramenta"),
                tool_call_id=request.tool_call.get("id", ""),
                status="success",
            )

        resposta = handler(request)

        if isinstance(resposta, ToolMessage) and getattr(
            resposta, "status", "success"
        ) != "error":
            with self._lock:
                if len(self._cache) >= self._MAX:
                    self._cache.pop(next(iter(self._cache)))

                self._cache[chave] = (str(resposta.content), agora)

        return resposta


class TratarErroDeTool(AgentMiddleware):
    """Devolve erros de ferramenta ao modelo em vez de encerrar a execução.

    Erros de validação (por exemplo, coluna inexistente) trazem mensagens
    que orientam a correção; assim o agente pode tentar novamente.
    """

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as erro:
            nome = request.tool_call.get("name", "ferramenta")

            return ToolMessage(
                content=(
                    f"Erro ao executar {nome}: {erro} "
                    f"Corrija os argumentos e tente novamente."
                ),
                name=nome,
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )


def _openrouter_extras() -> dict:
    """Extras do OpenRouter para melhorar cache de prompt e roteamento.

    Um ``session_id`` estável faz o OpenRouter usar roteamento fixo
    ("sticky"), aumentando os acertos de cache do prefixo.

    A fixação de provedor é opcional (``NLQ_PIN_PROVIDER=1``) e usa
    ``NLQ_PROVIDER`` (padrão ``DeepSeek``). Fica desligada por padrão
    porque fixar em um provedor pode rotear para um endpoint instável.
    """
    extras: dict = {
        "session_id": os.getenv("NLQ_SESSION_ID", "").strip()
        or f"nlq-{uuid.uuid4().hex}",
    }

    fixar = os.getenv("NLQ_PIN_PROVIDER", "0").strip().lower()

    if fixar in ("1", "true", "yes", "on"):
        provedor = os.getenv("NLQ_PROVIDER", "DeepSeek").strip() or "DeepSeek"
        extras["openrouter_provider"] = {
            "order": [provedor],
            "allow_fallbacks": True,
        }

    return extras


def _openrouter_reasoning() -> dict | None:
    """Configura o raciocínio do modelo no OpenRouter.

    Por padrão o raciocínio é mantido em canal separado
    (``additional_kwargs["reasoning_content"]``) e NÃO aparece no
    ``content``. Isso evita que o modelo "pense em voz alta" e
    despeje os passos no meio da resposta final.

    Controlado por ``NLQ_REASONING``:

    - ``separate`` (padrão): raciocínio em canal próprio (omite o
      parâmetro e deixa o comportamento padrão do provedor).
    - ``exclude``: o modelo raciocina, mas o raciocínio não é
      devolvido na resposta.
    - ``off``: desliga o raciocínio (mais rápido; em tarefas
      complexas o modelo pode narrar passos dentro do ``content``).
    """
    modo = os.getenv("NLQ_REASONING", "separate").strip().lower()

    if modo in ("off", "none", "disabled"):
        return {"enabled": False}

    if modo in ("exclude", "hidden"):
        return {"exclude": True}

    return None


def create_nlq_agent():
    checkpointer = InMemorySaver()

    usar_groq = (
        os.getenv("API_SELECT", "").strip().lower() == "groq"
        or not check_openrouter_key()
    )

    modelo_override = os.getenv("NLQ_MODEL", "").strip()
    max_tokens = int(os.getenv("NLQ_MAX_TOKENS", "5000"))

    if modelo_override:
        kwargs = {}

        if modelo_override.startswith("openrouter:"):
            kwargs.update(_openrouter_extras())

            reasoning = _openrouter_reasoning()
            if reasoning is not None:
                kwargs["reasoning"] = reasoning

        model = init_chat_model(
            modelo_override,
            temperature=0.1,
            timeout=60000,
            max_tokens=max_tokens,
            **kwargs,
        )
        print(
            f"[MODELO] Override (NLQ_MODEL): {modelo_override}",
            flush=True,
        )

    elif usar_groq:
        model = init_chat_model(
            "openai/gpt-oss-120b",
            model_provider="groq",
            temperature=0.1,
            timeout=60,
            max_tokens=max_tokens,
        )
        print("[MODELO] Groq: openai/gpt-oss-120b", flush=True)

    else:
        kwargs = _openrouter_extras()

        reasoning = _openrouter_reasoning()
        if reasoning is not None:
            kwargs["reasoning"] = reasoning

        model = init_chat_model(
            "openrouter:deepseek/deepseek-v4-flash-0731",
            temperature=0.1,
            timeout=60000,
            max_tokens=max_tokens,
            **kwargs,
        )
        print(
            f"[MODELO] OpenRouter: deepseek/deepseek-v4-flash-latest-0731",
            flush=True,
        )

    pasta_skills = skills_dir().resolve()
    arquivos_skills = sorted(pasta_skills.glob("*/SKILL.md"))

    if not arquivos_skills:
        raise RuntimeError(
            "Nenhuma skill encontrada. Esperado: "
            f"{pasta_skills}/nome-da-skill/SKILL.md"
        )

    print(f"[SKILLS] Pasta: {pasta_skills}", flush=True)

    for arquivo in arquivos_skills:
        print(
            f"[SKILLS] Encontrada no disco: {arquivo.parent.name}",
            flush=True,
        )

    tools = [
        create_json,
        goat,
        lista_arquivos,
        consultar_schema,
        buscar_semantico,
        consultar_dados,
    ]

    system_prompt = "\n\n".join(
        [
            load_prompt("system_base.md"),
            load_prompt("specific_role.md"),
            load_prompt("regra_consulta.md"),
        ]
    )

    # Poda algorítmica determinística: quando o histórico do thread excede
    # o gatilho (tokens aproximados), os resultados de ferramenta mais
    # antigos são substituídos por "[cleared]" na mensagem enviada ao
    # modelo. O checkpointer mantém o histórico completo, e o
    # CacheDeChamadas (TTL 300s) evita custo extra de re-execução caso o
    # modelo precise reconsultar algo podado.
    trigger = int(os.getenv("NLQ_CONTEXT_TRIGGER_TOKENS", "25000"))
    keep = int(os.getenv("NLQ_CONTEXT_KEEP_TOOL_RESULTS", "5"))

    #
    # Teto de chamadas de ferramenta por execução. Com
    # exit_behavior="continue" o modelo finaliza com o que já tem em vez
    # de travar. Suba para varreduras extensas (ex.: várias abas de uma
    # planilha grande), sob pena de respostas parciais.
    #
    run_limit = int(os.getenv("NLQ_TOOL_CALL_LIMIT", "25"))

    agent = create_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer,
        system_prompt=system_prompt,
        middleware=[
            CacheDeChamadas(),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=trigger,
                        keep=keep,
                    )
                ],
            ),
            ToolCallLimitMiddleware(
                run_limit=run_limit,
                exit_behavior="continue",
            ),
            TratarErroDeTool(),
        ],
    )

    return agent, checkpointer
