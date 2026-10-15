"""Pré-carregamento de recursos de consulta em segundo plano.

Move a leitura fria de planilhas (detecção de schema e carregamento de
registros) para trás da primeira chamada ao modelo, de modo que a
primeira ferramenta já encontre os dados em cache.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from .data.loader import get_schema, load_records
from .paths import data_dir


def _arquivos() -> Iterator[Path]:
    base = data_dir()

    for ext in ("xlsx", "csv"):
        pasta = base / ext

        if pasta.is_dir():
            yield from sorted(pasta.glob(f"*.{ext}"))


def aquecer() -> None:
    """Carrega schema e registros dos arquivos disponíveis."""
    for caminho in _arquivos():
        try:
            if caminho.suffix.lower() == ".xlsx":
                get_schema(caminho)
            load_records(caminho)
        except Exception as erro:
            print(
                f"[WARMUP] falha em {caminho.name}: {erro}",
                flush=True,
            )


def _executar() -> None:
    aquecer()
    print("[WARMUP] concluído", flush=True)


def aquecer_em_segundo_plano() -> threading.Thread:
    """Inicia o warm-up em uma thread daemon e retorna a thread."""
    thread = threading.Thread(
        target=_executar,
        name="nlq-warmup",
        daemon=True,
    )
    thread.start()
    return thread
