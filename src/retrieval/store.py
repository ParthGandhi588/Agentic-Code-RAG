"""PostgreSQL vector (pgvector) and full-text (tsvector) storage."""

from __future__ import annotations

from src.core.logger import setup_logger
from src.ingest.manifest import db_connection
from src.retrieval.models import ChunkRecord, SearchResult

logger = setup_logger("agentic-vector-store")

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_chunks (
    id BIGSERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    language VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    tsv_content tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_code_chunks_repo ON code_chunks(repo_id);
CREATE INDEX IF NOT EXISTS idx_code_chunks_tsv ON code_chunks USING gin (tsv_content);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
    ON code_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""


class VectorStore:
    """Unified PostgreSQL storage for vector embeddings and lexical tsvectors."""

    @staticmethod
    async def init_schema() -> None:
        """Initializes vector extension and code_chunks table in PostgreSQL."""
        try:
            async with db_connection() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("VectorStore schema initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize vector store schema: {e}")

    @staticmethod
    async def upsert_chunks(chunks: list[ChunkRecord], repo_id: str) -> None:
        """Inserts code chunks and their embeddings into PostgreSQL."""
        if not chunks:
            return

        query = """
            INSERT INTO code_chunks
                (repo_id, file_path, start_line, end_line, language, content, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::text::vector);
        """
        data = [
            (
                repo_id,
                c.file_path,
                c.start_line,
                c.end_line,
                c.language,
                c.content,
                str(c.embedding),
            )
            for c in chunks
            if c.embedding is not None
        ]
        try:
            async with db_connection() as conn:
                await conn.executemany(query, data)
            logger.info(f"VectorStore: Indexed {len(data)} chunks for repo '{repo_id}'")
        except Exception as e:
            logger.error(f"Failed to insert vector chunks: {e}")

    @staticmethod
    async def dense_search(
        query_vec: list[float], repo_id: str, limit: int = 30
    ) -> list[SearchResult]:
        """Cosine distance vector search via pgvector HNSW index."""
        query = """
            SELECT id, file_path, start_line, end_line, language, content,
                   1 - (embedding <=> $1::text::vector) AS similarity_score
            FROM code_chunks
            WHERE repo_id = $2
            ORDER BY embedding <=> $1::text::vector
            LIMIT $3;
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, str(query_vec), repo_id, limit)
                return [
                    SearchResult(
                        chunk_id=r["id"],
                        file_path=r["file_path"],
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        language=r["language"],
                        content=r["content"],
                        dense_score=float(r["similarity_score"]),
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"Dense vector search failed: {e}")
            return []

    @staticmethod
    async def sparse_search(query_text: str, repo_id: str, limit: int = 30) -> list[SearchResult]:
        """Lexical BM25 search via PostgreSQL tsvector and GIN index."""
        query = """
            SELECT id, file_path, start_line, end_line, language, content,
                   ts_rank_cd(tsv_content, plainto_tsquery('english', $1)) AS bm25_score
            FROM code_chunks
            WHERE repo_id = $2 AND tsv_content @@ plainto_tsquery('english', $1)
            ORDER BY bm25_score DESC
            LIMIT $3;
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, query_text, repo_id, limit)
                return [
                    SearchResult(
                        chunk_id=r["id"],
                        file_path=r["file_path"],
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        language=r["language"],
                        content=r["content"],
                        sparse_score=float(r["bm25_score"]),
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"Sparse lexical search failed: {e}")
            return []
