"""Data models for code chunking, vector embeddings, and search results."""

from __future__ import annotations

from pydantic import BaseModel


class ChunkRecord(BaseModel):
    """A chunk of source code prepared for embedding and storage."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    embedding: list[float] | None = None


class SearchResult(BaseModel):
    """A retrieved code chunk with scores from dense, sparse, and reranking stages."""

    chunk_id: int
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
