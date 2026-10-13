"""Geração de embeddings usando a API da OpenAI."""

from collections.abc import Sequence

from openai import OpenAI

from nlq.paths import load_env

load_env()

MODEL = "text-embedding-3-small"
BATCH_SIZE = 64


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Gera embeddings para uma sequência de textos."""
    if not texts:
        return []

    client = OpenAI()
    embeddings: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start : start + BATCH_SIZE])
        response = client.embeddings.create(
            model=MODEL,
            input=batch,
        )
        ordered_data = sorted(response.data, key=lambda item: item.index)
        embeddings.extend(item.embedding for item in ordered_data)

    return embeddings
