"""Busca semântica com índices mantidos em memória."""

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


def _get_index(path: str | Path) -> SemanticIndex:
    path = Path(path).resolve()
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size)

    cached = _INDEX_CACHE.get(path)

    if cached is not None and cached.fingerprint == fingerprint:
        return cached

    documents = build_documents(path)
    vectors = embed_texts(
        [document.page_content for document in documents]
    )

    index = SemanticIndex(
        fingerprint=fingerprint,
        documents=documents,
        vectors=vectors,
    )

    _INDEX_CACHE[path] = index
    return index


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

    query_vector = embed_texts([query])[0]

    ranked = [
        (
            document,
            _cosine_similarity(query_vector, vector),
        )
        for document, vector in zip(index.documents, index.vectors)
    ]

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
