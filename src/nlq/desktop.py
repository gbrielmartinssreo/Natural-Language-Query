"""Ponto de entrada do NLQ desktop (empacotado com PyInstaller).

Sobe a API FastAPI em ``127.0.0.1``, abre o navegador no endereço local
e encerra o processo de forma limpa quando a janela é fechada (Ctrl+C).
"""

from __future__ import annotations

import multiprocessing
import socket
import threading
import time
import webbrowser

HOST = "127.0.0.1"

# Porta inicial; se estiver ocupada, tenta as seguintes.
PORT_BASE = 8000
PORT_TENTATIVAS = 20


def _tentar_bind(host: str, port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None

    return sock


def escolher_socket(
    host: str = HOST,
    base: int = PORT_BASE,
    tentativas: int = PORT_TENTATIVAS,
) -> tuple[socket.socket, int]:
    """Socket livre a partir de ``base``; usa porta aleatória se preciso."""
    for offset in range(tentativas):
        sock = _tentar_bind(host, base + offset)

        if sock is not None:
            return sock, int(sock.getsockname()[1])

    sock = _tentar_bind(host, 0)

    if sock is None:
        raise RuntimeError("Não foi possível abrir uma porta local.")

    return sock, int(sock.getsockname()[1])


def preparar_pastas() -> None:
    """Garante as pastas externas de planilhas ao lado do executável."""
    from nlq.paths import data_dir

    for sub in ("csv", "xlsx"):
        (data_dir() / sub).mkdir(parents=True, exist_ok=True)


def _abrir_navegador(server, url: str) -> None:
    """Abre o navegador assim que o servidor estiver pronto."""
    while not server.started:
        if getattr(server, "should_exit", False):
            return
        time.sleep(0.1)

    webbrowser.open(url)


def main() -> None:
    # Carrega o .env antes de importar a API (o agente é criado no import).
    from nlq.paths import load_env

    load_env()
    preparar_pastas()

    import uvicorn

    from nlq.api import app

    sock, porta = escolher_socket()
    url = f"http://{HOST}:{porta}"

    config = uvicorn.Config(
        app,
        host=HOST,
        port=porta,
        log_level="info",
    )
    server = uvicorn.Server(config)

    threading.Thread(
        target=_abrir_navegador,
        args=(server, url),
        daemon=True,
    ).start()

    print(f"NLQ disponível em {url}")
    print("Pressione Ctrl+C para encerrar.")

    try:
        server.run(sockets=[sock])
    finally:
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
