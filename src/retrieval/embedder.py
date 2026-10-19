"""Local ONNX-accelerated embedding generator using FastEmbed."""

from __future__ import annotations

from fastembed import TextEmbedding

from src.core.config import get_settings
from src.core.logger import setup_logger

logger = setup_logger("agentic-embedder")
settings = get_settings()

_embed_model: TextEmbedding | None = None


def get_embed_model() -> TextEmbedding:
    """Initializes or returns cached singleton FastEmbed model."""
    global _embed_model
    if _embed_model is None:
        logger.info(f"Loading local embedding model: {settings.embed_model}...")
        _embed_model = TextEmbedding(model_name=settings.embed_model)
        logger.info("Embedding model ready.")
    return _embed_model


class FastEmbedder:
    """High-performance local vector generation."""

    @staticmethod
    def embed_query(query: str) -> list[float]:
        """Generates a normalized embedding for a search query."""
        model = get_embed_model()
        vectors = list(model.embed([query]))
        return [float(x) for x in vectors[0]]

    @staticmethod
    def embed_documents(texts: list[str]) -> list[list[float]]:
        """Generates embeddings for a batch of code documents."""
        if not texts:
            return []
        model = get_embed_model()
        vectors = list(model.embed(texts, batch_size=settings.embed_batch_size))
        return [[float(x) for x in v] for v in vectors]
