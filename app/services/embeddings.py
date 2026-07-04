"""Local embedding generation via sentence-transformers."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings

settings = get_settings()


@lru_cache
def get_model():
    """Load (and cache) the embedding model. Cached per-process."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed a batch of texts. Vectors are L2-normalized for cosine similarity."""
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
