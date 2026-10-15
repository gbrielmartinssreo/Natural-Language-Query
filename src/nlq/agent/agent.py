from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
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


REGRAS_DE_CONSULTA = """
POLÍTICA DE OPERAÇÃO:

Economia de etapas (prioridade máxima):
- Planeje antes de agir e emita chamadas independentes em paralelo numa
  MESMA rodada.
- Prefira UMA consulta suficiente a várias fragmentadas. Não faça uma
  consulta por aba: use aba="" para todas as abas.
- Consulte apenas as colunas necessárias; combine filtros na mesma
  chamada (AND).
- NÃO faça rodadas de conferência: agrupar e contar já trazem totais.
- NUNCA repita uma chamada idêntica. Faltou algo? Mude a estratégia ou
  informe a limitação.
- Reaproveite schema e dados já obtidos; finalize assim que a resposta
  estiver fundamentada.

Roteamento (escolha a ferramenta pelo objetivo):
- Abas, colunas e estrutura → consultar_schema (não por rotina).
- Filtros, contagens, somas, rankings, agrupamentos, valores distintos e
  metas → consultar_dados.
- Significado, sinônimos ou temas → buscar_semantico, apenas quando os
  critérios não forem verificáveis direto nas colunas.
- Descoberta de arquivos → lista_arquivos, só quando necessário.
- Extração completa de linhas → create_json, só se explicitamente pedido.

Dados:
- Diferencie registros, medidas e valores distintos; não confunda número
  de linhas com entidades únicas.
- Use apenas colunas e valores reais; nunca invente nem complete ausentes.
- Respeite limites/truncamento e diga quando o resultado for parcial.
- Preserve nomes originais e a aba de origem dos registros.

Resposta:
- Responda só o que foi perguntado, de forma concisa e direta.
- NÃO mostre passos, cálculos intermediários, índices/refs nem raciocínio;
  apresente somente o resultado final.
- Nunca repita a resposta nem seções.
"""

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


def create_nlq_agent():
    checkpointer = InMemorySaver()

    usar_groq = (
        os.getenv("API_SELECT", "").strip().lower() == "groq"
        or not check_openrouter_key()
    )

    modelo_override = os.getenv("NLQ_MODEL", "").strip()

    if modelo_override:
        kwargs = {}

        if modelo_override.startswith("openrouter:"):
            kwargs.update(_openrouter_extras())

            if "deepseek" in modelo_override:
                kwargs["reasoning"] = {"effort": "none"}

        model = init_chat_model(
            modelo_override,
            temperature=0.1,
            timeout=60000,
            max_tokens=2500,
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
            max_tokens=2500,
        )
        print("[MODELO] Groq: openai/gpt-oss-120b", flush=True)

    else:
        model = init_chat_model(
            "openrouter:deepseek/deepseek-v4-flash-0731",
            temperature=0.1,
            timeout=60000,
            max_tokens=2500,
            reasoning={"effort": "none"},
            **_openrouter_extras(),
        )
        print(
            "[MODELO] OpenRouter: deepseek/deepseek-v4-flash-latest-0731",
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
            REGRAS_DE_CONSULTA,
        ]
    )

    agent = create_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer,
        system_prompt=system_prompt,
        middleware=[
            CacheDeChamadas(),
            ToolCallLimitMiddleware(run_limit=10, exit_behavior="continue"),
            TratarErroDeTool(),
        ],
    )

    return agent, checkpointer
