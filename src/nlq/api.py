import json
import logging
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from nlq.agent.agent import create_nlq_agent

logger = logging.getLogger("nlq.api")

# Segundos sem dados antes de repetir um status (keep-alive da conexão).
KEEPALIVE_S = 10

# Tamanho da fila entre o worker e o gerador (backpressure).
FILA_MAX = 64

MENSAGEM_ERRO = "Não foi possível concluir a consulta."


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class LimparConversaRequest(BaseModel):
    thread_id: str


# api.py -> nlq -> src -> raiz do projeto
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

load_dotenv()

app = FastAPI()
agent, checkpointer = create_nlq_agent()


@app.get("/health")
def health():
    return {"status": "ok"}


def _ultima_planilha(result) -> dict | None:
    """Última planilha lida pelo agente na conversa (tool create_json)."""

    planilha = None

    for msg in result["messages"]:
        for tc in getattr(msg, "tool_calls", None) or []:
            nome = (
                tc.get("name")
                if isinstance(tc, dict)
                else getattr(tc, "name", None)
            )

            if nome != "create_json":
                continue

            args = (
                tc.get("args")
                if isinstance(tc, dict)
                else getattr(tc, "args", {}) or {}
            )

            if args.get("name"):
                planilha = {
                    "nome": args["name"],
                    "ext": args.get("ext"),
                }

    return planilha


def _linha(evento: dict) -> str:
    """Cada evento JSON termina com \\n para leitura linha a linha (NDJSON)."""

    return json.dumps(evento, ensure_ascii=False) + "\n"


def _status_do_estado(state) -> str:
    """Status genérico de execução a partir do estado atual do agente.

    Apenas estados abstratos: nenhum conteúdo de tool ou raciocínio da LLM.
    """

    messages = (state or {}).get("messages") or []

    if not messages:
        return "processando"

    ultimo = messages[-1]

    if isinstance(ultimo, ToolMessage):
        return "executando ferramenta"

    if getattr(ultimo, "tool_calls", None):
        return "executando ferramenta"

    return "consultando modelo"


def _texto_final(mensagem) -> str:
    """Texto da mensagem final do agente (somente blocos de texto)."""

    content = getattr(mensagem, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        partes = []

        for bloco in content:
            if isinstance(bloco, str):
                partes.append(bloco)

            elif (
                isinstance(bloco, dict)
                and bloco.get("type") == "text"
            ):
                partes.append(bloco.get("text") or "")

        return "".join(partes)

    return str(content)


@app.post("/api/chat")
def chat(request: ChatRequest):
    config = {
        "configurable": {
            "thread_id": request.thread_id,
        }
    }

    entrada = {
        "messages": [
            {
                "role": "user",
                "content": f"\nUser: {request.message}",
            }
        ]
    }

    def generate():
        # Primeiro byte imediato: evita o H12 do Heroku.
        yield _linha(
            {
                "type": "status",
                "content": "processando",
            }
        )

        # O agente roda em uma thread própria; o gerador consome a fila
        # e emite um keep-alive caso nada chegue por alguns segundos.
        # Assim a conexão nunca fica parada durante consultas longas.
        fila: queue.Queue = queue.Queue(maxsize=FILA_MAX)
        parar = threading.Event()

        def publicar(item) -> None:
            while not parar.is_set():
                try:
                    fila.put(item, timeout=1)
                    return

                except queue.Full:
                    continue

        def executar() -> None:
            try:
                ultimo_estado = None

                for estado in agent.stream(
                    entrada,
                    config=config,
                    # "values": estado completo a cada etapa do grafo.
                    stream_mode="values",
                ):
                    ultimo_estado = estado
                    publicar(("estado", estado))

                publicar(("fim", ultimo_estado))

            except Exception:
                logger.exception("Erro durante o streaming do agente")
                publicar(("erro", None))

        threading.Thread(
            target=executar,
            daemon=True,
        ).start()

        ultimo_status = "processando"

        try:
            while True:
                try:
                    tipo, payload = fila.get(
                        timeout=KEEPALIVE_S
                    )

                except queue.Empty:
                    # Keep-alive: mantém a stream ativa.
                    yield _linha(
                        {
                            "type": "status",
                            "content": ultimo_status,
                        }
                    )
                    continue

                if tipo == "estado":
                    status = _status_do_estado(payload)

                    if status != ultimo_status:
                        ultimo_status = status

                        yield _linha(
                            {
                                "type": "status",
                                "content": status,
                            }
                        )

                elif tipo == "fim":
                    if not payload or not payload.get(
                        "messages"
                    ):
                        yield _linha(
                            {
                                "type": "error",
                                "message": MENSAGEM_ERRO,
                            }
                        )
                        return

                    yield _linha(
                        {
                            "type": "result",
                            "response": _texto_final(
                                payload["messages"][-1]
                            ),
                            "planilha": _ultima_planilha(
                                payload
                            ),
                        }
                    )
                    return

                else:
                    # "erro" do worker ou evento inesperado.
                    yield _linha(
                        {
                            "type": "error",
                            "message": MENSAGEM_ERRO,
                        }
                    )
                    return

        finally:
            # Cliente desconectou (H18) ou stream encerrada:
            # sinaliza para o worker parar de publicar.
            parar.set()

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/limpar-conversa")
def clear_chat(request: LimparConversaRequest):
    checkpointer.delete_thread(request.thread_id)

    return {
        "status": "ok",
    }


app.mount(
    "/",
    StaticFiles(
        directory=FRONTEND_DIR,
        html=True,
    ),
    name="frontend",
)
