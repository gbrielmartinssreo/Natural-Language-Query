"""Geração de embeddings usando a API da OpenAI."""

from collections.abc import Sequence
from time import perf_counter

from openai import OpenAI

from nlq.paths import load_env

load_env()

MODEL = "text-embedding-3-small"
BATCH_SIZE = 64

client = OpenAI()


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Gera embeddings para uma sequência de textos."""
    if not texts:
        return []

    embeddings: list[list[float]] = []
    inicio_total = perf_counter()

    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start:start + BATCH_SIZE])
        inicio = perf_counter()

        response = client.embeddings.create(
            model=MODEL,
            input=batch,
        )

        tempo = perf_counter() - inicio

        tokens = (
            response.usage.total_tokens
            if response.usage
            else "indisponível"
        )

        print(
            f"[EMBED] lote={start // BATCH_SIZE + 1} "
            f"textos={len(batch)} "
            f"tempo={tempo:.3f}s "
            f"tokens={tokens}",
            flush=True,
        )

        ordered_data = sorted(
            response.data,
            key=lambda item: item.index,
        )

        embeddings.extend(
            item.embedding for item in ordered_data
        )

    print(
        f"[EMBED] TOTAL textos={len(texts)} "
        f"tempo={perf_counter() - inicio_total:.3f}s",
        flush=True,
    )

    return embeddings
