import asyncio
import json
import logging
import queue
import threading
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.errors import GraphDrained
from langgraph.runtime import RunControl
from pydantic import BaseModel

from nlq.agent.agent import create_nlq_agent
from nlq.attachments import (
    MAX_FILE_BYTES,
    add_attachment,
    conversation_scope,
    delete_all,
    delete_attachment,
    list_attachments,
    sweep_expired,
    touch_message,
    validate_thread_id,
)
from nlq.data.semantic_search import limpar_indices
from nlq.data.loader import clear_cache as limpar_cache_loader
from nlq.paths import frontend_dir, load_env
from nlq.tools.consultar_dados import limpar_cache_dataframes
from nlq.warmup import aquecer_em_segundo_plano


logger = logging.getLogger("nlq.api")

# Segundos sem dados antes de enviar um keep-alive.
KEEPALIVE_S = 10

# Tamanho máximo da fila entre worker e gerador.
FILA_MAX = 64

# Intervalo entre verificações de desconexão do cliente.
POLL_S = 0.1

# Tamanho do lote de tokens antes de publicar um evento.
# Evita uma linha NDJSON por token do modelo.
TAMANHO_LOTE_TOKEN = 24

MENSAGEM_ERRO = "Não foi possível concluir a consulta."


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class LimparConversaRequest(BaseModel):
    thread_id: str


# Frontend empacotado ou no repositório (ver nlq/paths.py).
FRONTEND_DIR = frontend_dir()

load_env()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(sweep_expired)
    task = asyncio.create_task(_limpar_expirados_periodicamente())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)

agent, checkpointer = create_nlq_agent()


@app.middleware("http")
async def limitar_upload(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/anexos":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > MAX_FILE_BYTES + 1024 * 1024
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "O arquivo excede o limite permitido."},
                )
    return await call_next(request)

# Pré-carrega schema e registros em segundo plano para que a primeira
# consulta não pague a leitura fria das planilhas.
aquecer_em_segundo_plano()

# Conversas com uma consulta em andamento.
#
# A limpeza do histórico é bloqueada enquanto a consulta roda,
# para não apagar um thread que o agente ainda está usando.
_consultas_ativas: set[str] = set()
_consultas_lock = threading.Lock()


@dataclass
class _ExecucaoAtiva:
    cancelado: threading.Event
    control: RunControl
    concluido: threading.Event


_execucoes_ativas: dict[str, _ExecucaoAtiva] = {}


async def _limpar_expirados_periodicamente() -> None:
    while True:
        await asyncio.sleep(15 * 60)
        await asyncio.to_thread(sweep_expired)


def _cancelar_execucao(thread_id: str, timeout: float = 15.0) -> bool:
    with _consultas_lock:
        execution = _execucoes_ativas.get(thread_id)
        marked_active = thread_id in _consultas_ativas
    if execution is None:
        return not marked_active
    execution.cancelado.set()
    execution.control.request_drain("attachment_lifecycle")
    return execution.concluido.wait(timeout)


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


def _separar_evento(item) -> tuple[str, object]:
    """
    Normaliza um item do stream do LangGraph em (modo, payload).

    Com ``stream_mode=["messages", "values"]`` o LangGraph entrega
    tuplas ``(modo, payload)``. Quando ``stream_mode`` é uma string
    única, entrega apenas o payload — tratado como "values".
    """

    if (
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], str)
    ):
        return item[0], item[1]

    return "values", item


def _token_do_chunk(payload) -> str:
    """
    Extrai o texto de um chunk de token do modo "messages".

    Ignora chunks de chamada de ferramenta (argumentos JSON) e
    conteúdos que não sejam texto, para não vazar dados internos.
    """

    if not isinstance(payload, tuple) or len(payload) != 2:
        return ""

    chunk, _metadata = payload

    # O modo "messages" também emite mensagens de ferramenta;
    # apenas tokens do próprio modelo são transmitidos.
    if not isinstance(chunk, AIMessageChunk):
        return ""

    if getattr(chunk, "tool_call_chunks", None):
        return ""

    content = getattr(chunk, "content", "")

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

    return ""


def _reasoning_do_chunk(payload) -> str:
    """
    Extrai o raciocínio (``reasoning_content``) de um chunk do modo
    "messages".

    Modelos com raciocínio (ex.: DeepSeek no OpenRouter) enviam o
    "pensar em voz alta" em ``additional_kwargs["reasoning_content"]``,
    separado do ``content``. Devolvemos esse texto para exibi-lo à parte,
    sem contaminar a resposta final.
    """

    if not isinstance(payload, tuple) or len(payload) != 2:
        return ""

    chunk, _metadata = payload

    if not isinstance(chunk, AIMessageChunk):
        return ""

    extras = getattr(chunk, "additional_kwargs", None) or {}

    raciocinio = extras.get("reasoning_content")

    if isinstance(raciocinio, str):
        return raciocinio

    if isinstance(raciocinio, list):
        partes = []

        for bloco in raciocinio:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif (
                isinstance(bloco, dict)
                and bloco.get("type") == "text"
            ):
                partes.append(bloco.get("text") or "")

        return "".join(partes)

    return ""


def _executar_agente(
    agente,
    entrada: dict,
    config: dict,
    publicar,
    cancelado: threading.Event,
    control: RunControl,
    thread_id: str = "00000000-0000-0000-0000-000000000000",
    concluido: threading.Event | None = None,
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

    scope = conversation_scope(thread_id)
    scope.__enter__()

    try:

        ultimo_estado = None
        buffer_tokens: list[str] = []
        buffer_thinking: list[str] = []

        def enviar_tokens() -> None:
            """Publica o lote acumulado de tokens (se houver)."""
            if buffer_tokens:
                publicar(("token", "".join(buffer_tokens)))
                buffer_tokens.clear()

        def enviar_thinking() -> None:
            """Publica o lote acumulado de raciocínio (se houver)."""
            if buffer_thinking:
                publicar(("thinking", "".join(buffer_thinking)))
                buffer_thinking.clear()

        t_agent = time.perf_counter()

        for item in agente.stream(
            entrada,
            config=config,
            stream_mode=["messages", "values"],
            control=control,
        ):

            if cancelado.is_set():
                break

            modo, payload = _separar_evento(item)

            if modo == "messages":
                token = _token_do_chunk(payload)

                if token:
                    buffer_tokens.append(token)

                    if sum(map(len, buffer_tokens)) >= TAMANHO_LOTE_TOKEN:
                        enviar_tokens()

                raciocinio = _reasoning_do_chunk(payload)

                if raciocinio:
                    buffer_thinking.append(raciocinio)

                    if (
                        sum(map(len, buffer_thinking))
                        >= TAMANHO_LOTE_TOKEN
                    ):
                        enviar_thinking()

                continue

            # Modo "values": estado consolidado após o superstep.
            enviar_tokens()
            enviar_thinking()
            ultimo_estado = payload

            status = _status_do_estado(
                payload
            )

            publicar(
                (
                    "status",
                    status,
                )
            )

        enviar_tokens()
        enviar_thinking()

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
    finally:
        scope.__exit__(None, None, None)
        with _consultas_lock:
            execution = _execucoes_ativas.get(thread_id)
            if execution is not None and execution.concluido is concluido:
                _execucoes_ativas.pop(thread_id, None)
                _consultas_ativas.discard(thread_id)
        if concluido is not None:
            concluido.set()


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
):
    try:
        thread_id = validate_thread_id(request.thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    touch_message(thread_id)

    config = {
        "configurable": {
            "thread_id":
                thread_id,
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
        concluido = threading.Event()
        execution = _ExecucaoAtiva(cancelado, control, concluido)

        with _consultas_lock:
            if thread_id in _execucoes_ativas:
                yield _linha({
                    "type": "error",
                    "message": "Já há uma consulta nesta conversa.",
                })
                return
            _consultas_ativas.add(thread_id)
            _execucoes_ativas[thread_id] = execution

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
                    thread_id,
                    concluido,
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

                    if cancelado.is_set() and concluido.is_set():
                        return

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
                # TOKENS DA RESPOSTA (streaming parcial)
                #
                elif tipo == "token":

                    if payload:

                        yield _linha(
                            {
                                "type":
                                    "token",
                                "content":
                                    payload,
                            }
                        )

                #
                # RACIOCÍNIO DO MODELO (canal separado)
                #
                elif tipo == "thinking":

                    if payload:

                        yield _linha(
                            {
                                "type":
                                    "thinking",
                                "content":
                                    payload,
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
    try:
        thread_id = validate_thread_id(request.thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not _cancelar_execucao(thread_id):
        return JSONResponse(
            status_code=409,
            content={
                "status": "erro",
                "message": "Não foi possível interromper a consulta em andamento.",
            },
        )

    checkpointer.delete_thread(thread_id)
    delete_all(thread_id)

    return {
        "status": "ok",
    }


@app.get("/api/anexos")
def get_attachments(thread_id: str):
    try:
        return {"anexos": list_attachments(thread_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/anexos", status_code=201)
def upload_attachment(
    thread_id: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        normalized = validate_thread_id(thread_id)
        with _consultas_lock:
            if normalized in _consultas_ativas:
                raise HTTPException(
                    status_code=409,
                    detail="Aguarde a consulta terminar antes de anexar outro arquivo.",
                )
        attachment = add_attachment(normalized, file.filename or "", file.file)
        return {"status": "ok", "anexo": attachment}
    except ValueError as exc:
        status = 413 if "excede o limite" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    finally:
        file.file.close()


@app.delete("/api/anexos/{attachment_id}")
def remove_attachment(attachment_id: str, thread_id: str):
    try:
        thread_id = validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not _cancelar_execucao(thread_id):
        raise HTTPException(
            status_code=409,
            detail="Não foi possível interromper a consulta em andamento.",
        )
    if not delete_attachment(thread_id, attachment_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    return {"status": "ok"}


@app.delete("/api/limpar-cache")
def clear_cache():

    with _consultas_lock:
        ativas = len(_consultas_ativas)

    #
    # Não apaga os caches enquanto há consulta em andamento: o agente
    # pode estar lendo um índice semântico ou um DataFrame no momento.
    #
    if ativas:

        return JSONResponse(
            status_code=409,
            content={
                "status": "erro",
                "message": (
                    "Há consulta em andamento; "
                    "aguarde antes de limpar os caches."
                ),
            },
        )

    dataframes = limpar_cache_dataframes()
    limpar_cache_loader()
    semantica = limpar_indices(disco=True)

    return {
        "status": "ok",
        "dataframes_ram": dataframes,
        **semantica,
    }


app.mount(
    "/",
    StaticFiles(
        directory=FRONTEND_DIR,
        html=True,
    ),
    name="frontend",
)
