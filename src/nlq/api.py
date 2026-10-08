import json
import logging
import queue
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from nlq.agent.agent import create_nlq_agent


logger = logging.getLogger("nlq.api")

# Segundos sem dados antes de enviar um keep-alive.
KEEPALIVE_S = 10

# Tamanho máximo da fila entre worker e gerador.
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
    return {
        "status": "ok",
    }


def _ultima_planilha(result) -> dict | None:
    """Última planilha lida pelo agente na conversa."""

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
    """
    Serializa um evento como NDJSON.

    Cada evento termina com \n para o frontend
    conseguir processar linha por linha.
    """

    return json.dumps(
        evento,
        ensure_ascii=False,
    ) + "\n"


def _status_do_estado(state) -> str:
    """
    Retorna apenas um status genérico do agente.

    Não expõe conteúdo das tools nem raciocínio interno.
    """

    messages = (
        (state or {}).get("messages")
        or []
    )

    if not messages:
        return "processando"

    ultimo = messages[-1]

    if isinstance(
        ultimo,
        ToolMessage,
    ):
        return "executando ferramenta"

    if getattr(
        ultimo,
        "tool_calls",
        None,
    ):
        return "executando ferramenta"

    return "consultando modelo"


def _texto_final(mensagem) -> str:
    """
    Extrai apenas texto da mensagem final.
    """

    content = getattr(
        mensagem,
        "content",
        "",
    )

    if isinstance(
        content,
        str,
    ):
        return content

    if isinstance(
        content,
        list,
    ):
        partes = []

        for bloco in content:

            if isinstance(
                bloco,
                str,
            ):
                partes.append(
                    bloco
                )

            elif (
                isinstance(
                    bloco,
                    dict,
                )
                and bloco.get("type")
                == "text"
            ):
                partes.append(
                    bloco.get("text")
                    or ""
                )

        return "".join(
            partes
        )

    return str(content)


@app.post("/api/chat")
def chat(request: ChatRequest):

    config = {
        "configurable": {
            "thread_id":
                request.thread_id,
        }
    }

    entrada = {
        "messages": [
            {
                "role": "user",
                "content":
                    f"\nUser: {request.message}",
            }
        ]
    }

    def generate():

        #
        # PRIMEIRO BYTE
        #
        # Sai imediatamente para evitar H12.
        #
        yield _linha(
            {
                "type": "status",
                "content": "processando",
            }
        )

        #
        # Comunicação entre:
        #
        # thread do agente
        #       ↓
        #     queue
        #       ↓
        # StreamingResponse
        #
        fila: queue.Queue = queue.Queue(
            maxsize=FILA_MAX
        )

        parar = threading.Event()

        def publicar(item) -> None:
            """
            Publica evento na fila sem bloquear
            indefinidamente caso o cliente desconecte.
            """

            while not parar.is_set():

                try:
                    fila.put(
                        item,
                        timeout=1,
                    )

                    return

                except queue.Full:
                    continue

        def executar() -> None:
            """
            Executa o agente em thread separada.

            Importante:
            não colocamos o estado completo do LangGraph
            na fila a cada evento.

            A fila recebe apenas pequenos status.
            """

            try:

                ultimo_estado = None

                t_agent = time.perf_counter()

                for estado in agent.stream(
                    entrada,
                    config=config,
                    stream_mode="values",
                ):

                    ultimo_estado = estado

                    status = _status_do_estado(
                        estado
                    )

                    publicar(
                        (
                            "status",
                            status,
                        )
                    )

                duracao = (
                    time.perf_counter()
                    - t_agent
                )

                print(
                    f"[PERF] agent.stream: "
                    f"{duracao:.2f}s",
                    flush=True,
                )

                #
                # Apenas o estado FINAL é enviado
                # pela fila.
                #
                publicar(
                    (
                        "fim",
                        ultimo_estado,
                    )
                )

            except Exception:

                logger.exception(
                    "Erro durante o streaming do agente"
                )

                publicar(
                    (
                        "erro",
                        None,
                    )
                )

        #
        # Inicia agente em paralelo.
        #
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

                    #
                    # KEEP-ALIVE
                    #
                    # Se nenhuma etapa do agente produzir
                    # evento em 10 segundos, enviamos algo
                    # mesmo assim.
                    #
                    # Isso evita o H15 por conexão ociosa.
                    #

                    print(
                        f"[KEEPALIVE] enviado "
                        f"status={ultimo_status}",
                        flush=True,
                    )

                    yield _linha(
                        {
                            "type": "ping",
                            "status":
                                ultimo_status,
                        }
                    )

                    continue

                #
                # STATUS DO AGENTE
                #
                if tipo == "status":

                    status = payload

                    if (
                        status
                        != ultimo_status
                    ):

                        ultimo_status = status

                        print(
                            f"[STREAM] status="
                            f"{status}",
                            flush=True,
                        )

                        yield _linha(
                            {
                                "type":
                                    "status",
                                "content":
                                    status,
                            }
                        )

                #
                # PROCESSAMENTO TERMINOU
                #
                elif tipo == "fim":

                    if (
                        not payload
                        or not payload.get(
                            "messages"
                        )
                    ):

                        yield _linha(
                            {
                                "type":
                                    "error",
                                "message":
                                    MENSAGEM_ERRO,
                            }
                        )

                        return

                    response = (
                        _texto_final(
                            payload[
                                "messages"
                            ][-1]
                        )
                    )

                    planilha = (
                        _ultima_planilha(
                            payload
                        )
                    )

                    print(
                        "[STREAM] resultado final enviado",
                        flush=True,
                    )

                    yield _linha(
                        {
                            "type":
                                "result",
                            "response":
                                response,
                            "planilha":
                                planilha,
                        }
                    )

                    return

                #
                # ERRO NO WORKER
                #
                elif tipo == "erro":

                    print(
                        "[STREAM] erro enviado ao cliente",
                        flush=True,
                    )

                    yield _linha(
                        {
                            "type":
                                "error",
                            "message":
                                MENSAGEM_ERRO,
                        }
                    )

                    return

                #
                # EVENTO INESPERADO
                #
                else:

                    logger.warning(
                        "Evento inesperado na fila: %s",
                        tipo,
                    )

                    yield _linha(
                        {
                            "type":
                                "error",
                            "message":
                                MENSAGEM_ERRO,
                        }
                    )

                    return

        finally:

            #
            # Cliente desconectou ou a resposta terminou.
            #
            parar.set()

            print(
                "[STREAM] encerrado",
                flush=True,
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control":
                "no-cache",
            "X-Accel-Buffering":
                "no",
        },
    )


@app.delete("/api/limpar-conversa")
def clear_chat(
    request: LimparConversaRequest,
):

    checkpointer.delete_thread(
        request.thread_id
    )

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
