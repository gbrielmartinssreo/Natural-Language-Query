import asyncio
import json
import logging
import queue
import threading
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphDrained
from langgraph.runtime import RunControl
from pydantic import BaseModel

from nlq.agent.agent import create_nlq_agent
from nlq.paths import frontend_dir, load_env


logger = logging.getLogger("nlq.api")

# Segundos sem dados antes de enviar um keep-alive.
KEEPALIVE_S = 10

# Tamanho máximo da fila entre worker e gerador.
FILA_MAX = 64

# Intervalo entre verificações de desconexão do cliente.
POLL_S = 0.1

MENSAGEM_ERRO = "Não foi possível concluir a consulta."


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class LimparConversaRequest(BaseModel):
    thread_id: str


# Frontend empacotado ou no repositório (ver nlq/paths.py).
FRONTEND_DIR = frontend_dir()

load_env()

app = FastAPI()

agent, checkpointer = create_nlq_agent()

# Conversas com uma consulta em andamento.
#
# A limpeza do histórico é bloqueada enquanto a consulta roda,
# para não apagar um thread que o agente ainda está usando.
_consultas_ativas: set[str] = set()
_consultas_lock = threading.Lock()


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


def _executar_agente(
    agente,
    entrada: dict,
    config: dict,
    publicar,
    cancelado: threading.Event,
    control: RunControl,
) -> None:
    """
    Executa o agente em thread separada.

    Importante:
    não colocamos o estado completo do LangGraph
    na fila a cada evento.

    A fila recebe apenas pequenos status.

    O cancelamento é cooperativo: `control.request_drain()`
    faz o LangGraph parar no próximo limite de superstep,
    sem matar a thread.
    """

    try:

        ultimo_estado = None

        t_agent = time.perf_counter()

        for estado in agente.stream(
            entrada,
            config=config,
            stream_mode="values",
            control=control,
        ):

            if cancelado.is_set():
                break

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

        if cancelado.is_set():
            return

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

    except GraphDrained as exc:

        #
        # Cancelamento cooperativo: o cliente desconectou
        # e pedimos o drain. Não é uma falha inesperada.
        #
        print(
            f"[CANCEL] execução interrompida: {exc}",
            flush=True,
        )

    except Exception:

        if cancelado.is_set():
            return

        logger.exception(
            "Erro durante o streaming do agente"
        )

        publicar(
            (
                "erro",
                None,
            )
        )


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
):

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

    async def generate():

        #
        # Registra a consulta como ativa enquanto o stream existir.
        #
        with _consultas_lock:
            _consultas_ativas.add(
                request.thread_id
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

        #
        # Cancelamento POR EXECUÇÃO.
        #
        # Cada consulta cria o seu próprio Event e o seu
        # próprio RunControl — nada é compartilhado entre
        # consultas diferentes.
        #
        cancelado = threading.Event()
        control = RunControl()

        def publicar(item) -> None:
            """
            Publica evento na fila sem bloquear
            indefinidamente caso o cliente desconecte.
            """

            while not cancelado.is_set():

                try:
                    fila.put(
                        item,
                        timeout=1,
                    )

                    return

                except queue.Full:
                    continue

        ultimo_status = "processando"
        ultimo_ping = time.monotonic()

        try:

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
            # Inicia agente em paralelo.
            #
            threading.Thread(
                target=_executar_agente,
                args=(
                    agent,
                    entrada,
                    config,
                    publicar,
                    cancelado,
                    control,
                ),
                daemon=True,
            ).start()

            while True:

                #
                # Cliente desconectou: para de enviar e
                # pede o cancelamento cooperativo.
                #
                if await http_request.is_disconnected():

                    print(
                        "[STREAM] cliente desconectou",
                        flush=True,
                    )

                    return

                try:

                    tipo, payload = fila.get_nowait()

                except queue.Empty:

                    #
                    # KEEP-ALIVE
                    #
                    # Se nenhuma etapa do agente produzir
                    # evento por KEEPALIVE_S, enviamos algo
                    # mesmo assim.
                    #
                    # Isso evita o H15 por conexão ociosa.
                    #
                    if (
                        time.monotonic()
                        - ultimo_ping
                    ) >= KEEPALIVE_S:

                        ultimo_ping = time.monotonic()

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

                    await asyncio.sleep(POLL_S)

                    continue

                ultimo_ping = time.monotonic()

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

        except (asyncio.CancelledError, GeneratorExit):

            #
            # Encerramento da conexão. Não é uma falha
            # inesperada — apenas propagamos depois da limpeza.
            #
            print(
                "[STREAM] requisição cancelada pelo cliente",
                flush=True,
            )

            raise

        finally:

            #
            # Cliente desconectou ou a resposta terminou.
            #
            # Sinaliza o worker e pede o drain cooperativo para
            # que ele não inicie novas etapas.
            #
            cancelado.set()

            control.request_drain(
                "client_disconnect"
            )

            #
            # Libera eventos pendentes da fila abandonada.
            #
            try:
                while True:
                    fila.get_nowait()
            except queue.Empty:
                pass

            with _consultas_lock:
                _consultas_ativas.discard(
                    request.thread_id
                )

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

    with _consultas_lock:
        ativa = (
            request.thread_id
            in _consultas_ativas
        )

    #
    # Não apaga a conversa enquanto o agente usa o thread.
    #
    if ativa:

        return JSONResponse(
            status_code=409,
            content={
                "status": "erro",
                "message": (
                    "Há uma consulta em andamento "
                    "para esta conversa."
                ),
            },
        )

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
