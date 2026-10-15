"""Busca semântica com índices mantidos em memória e em disco."""

import hashlib
import os
import pickle
import tempfile
import threading
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from langchain_core.documents import Document

from .documents import build_documents
from .embeddings import embed_texts


@dataclass
class SemanticIndex:
    fingerprint: tuple[int, int]
    documents: list[Document]
    vectors: list[list[float]]


# Um índice por caminho de arquivo.
_INDEX_CACHE: dict[Path, SemanticIndex] = {}

# Serializa a construção do índice: chamadas concorrentes para o mesmo
# arquivo reutilizam o primeiro resultado em vez de reconstruí-lo.
_INDEX_LOCK = threading.Lock()

# Cache de embeddings de consulta (independente do arquivo).
_QUERY_CACHE: dict[str, list[float]] = {}
_QUERY_CACHE_MAX = 256


# Versão do formato do cache em disco. Mude quando a lógica de
# construção dos documentos/vetores mudar.
_CACHE_VERSION = 1


def _cache_dir() -> Path:
    base = os.getenv("XDG_CACHE_HOME") or tempfile.gettempdir()
    return Path(base) / "nlq-cache"


def _cache_file(path: Path, fingerprint: tuple[int, int]) -> Path:
    raw = (
        f"{_CACHE_VERSION}|{path}|{fingerprint[0]}|{fingerprint[1]}"
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return _cache_dir() / f"index-{digest}.pkl"


def _load_index_from_disk(
    path: Path,
    fingerprint: tuple[int, int],
) -> SemanticIndex | None:
    """Carrega um índice persistido, se ele corresponder ao arquivo."""
    try:
        cache_file = _cache_file(path, fingerprint)

        if not cache_file.is_file():
            return None

        with cache_file.open("rb") as arquivo:
            data = pickle.load(arquivo)

        if data.get("fingerprint") != fingerprint:
            return None

        return SemanticIndex(
            fingerprint=fingerprint,
            documents=data["documents"],
            vectors=data["vectors"],
        )
    except Exception:
        # Cache corrompido ou incompatível: reconstrói do zero.
        return None


def _save_index_to_disk(path: Path, index: SemanticIndex) -> None:
    """Persiste o índice para reutilização em execuções futuras."""
    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = _cache_file(path, index.fingerprint)
        temporario = cache_file.with_suffix(".tmp")

        with temporario.open("wb") as arquivo:
            pickle.dump(
                {
                    "fingerprint": index.fingerprint,
                    "documents": index.documents,
                    "vectors": index.vectors,
                },
                arquivo,
            )

        os.replace(temporario, cache_file)
    except Exception:
        # Persistência é opcional: falhas não devem quebrar a busca.
        pass


def _get_index(path: str | Path) -> SemanticIndex:
    path = Path(path).resolve()
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size)

    cached = _INDEX_CACHE.get(path)

    if cached is not None and cached.fingerprint == fingerprint:
        return cached

    with _INDEX_LOCK:
        # Outra thread pode ter construído o índice enquanto esperávamos.
        cached = _INDEX_CACHE.get(path)

        if cached is not None and cached.fingerprint == fingerprint:
            return cached

        index = _load_index_from_disk(path, fingerprint)

        if index is None:
            documents = build_documents(path)
            vectors = embed_texts(
                [document.page_content for document in documents]
            )

            index = SemanticIndex(
                fingerprint=fingerprint,
                documents=documents,
                vectors=vectors,
            )

            _save_index_to_disk(path, index)

        _INDEX_CACHE[path] = index
        return index


def warm_index(path: str | Path) -> None:
    """Pré-carrega o índice de um arquivo (uso em warm-up)."""
    _get_index(path)


def limpar_indices(disco: bool = True) -> dict:
    """Libera os caches de busca semântica (RAM e, opcionalmente, disco).

    Zera os índices e os embeddings de consulta mantidos em memória e,
    com ``disco=True``, apaga os ``index-*.pkl`` persistidos.

    A próxima busca semântica reconstrói o índice sob demanda (o que
    custa novas chamadas de embedding). Não usar com consultas ativas.
    """

    liberado: dict = {
        "indice_ram": len(_INDEX_CACHE),
        "consulta_ram": len(_QUERY_CACHE),
        "arquivos_disco": 0,
        "bytes_disco": 0,
    }

    _INDEX_CACHE.clear()
    _QUERY_CACHE.clear()

    if disco:
        pasta = _cache_dir()

        if pasta.is_dir():
            for arquivo in pasta.glob("index-*.pkl"):
                try:
                    liberado["bytes_disco"] += arquivo.stat().st_size
                    arquivo.unlink()
                    liberado["arquivos_disco"] += 1
                except OSError:
                    # Arquivo em uso ou já removido: segue a limpeza.
                    pass

    return liberado


def _embed_query(query: str) -> list[float]:
    """Gera (ou reaproveita) o embedding de uma consulta."""
    cached = _QUERY_CACHE.get(query)

    if cached is not None:
        return cached

    vector = embed_texts([query])[0]

    if len(_QUERY_CACHE) >= _QUERY_CACHE_MAX:
        _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))

    _QUERY_CACHE[query] = vector
    return vector


def _cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = sqrt(sum(value * value for value in vector_a))
    norm_b = sqrt(sum(value * value for value in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def search_documents(
    path: str | Path,
    query: str,
    top_k: int = 5,
) -> list[tuple[Document, float]]:
    """Retorna os documentos mais semelhantes à pergunta."""
    if not query.strip():
        return []

    if top_k < 1:
        raise ValueError("top_k deve ser maior que zero")

    index = _get_index(path)

    if not index.documents:
        return []

    query_vector = _embed_query(query)

    ranked = [
        (
            document,
            _cosine_similarity(query_vector, vector),
        )
        for document, vector in zip(index.documents, index.vectors)
    ]

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
