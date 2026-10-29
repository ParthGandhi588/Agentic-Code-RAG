"""PostgreSQL database manifest tracking indexed repository files."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg

from src.core.config import get_settings
from src.core.disk_cache import load_cache, save_cache
from src.core.logger import setup_logger
from src.ingest.models import ScannedFile

logger = setup_logger("agentic-manifest")
settings = get_settings()

_pool: asyncpg.Pool | None = None
_db_offline: bool = False
_last_db_error_time: float = 0.0


async def get_db_pool() -> asyncpg.Pool:
    """Initializes and returns the shared asyncpg connection pool with fail-fast offline resilience."""
    global _pool, _db_offline, _last_db_error_time
    if _db_offline and (time.time() - _last_db_error_time < 30.0):
        raise ConnectionError("PostgreSQL database is currently offline.")

    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                host=settings.pg_host,
                port=settings.pg_port,
                user=settings.pg_user,
                password=settings.pg_password,
                database=settings.pg_database,
                min_size=1,
                max_size=10,
                timeout=1.0,
                command_timeout=3.0,
            )
            _db_offline = False
        except Exception as e:
            _db_offline = True
            _last_db_error_time = time.time()
            logger.debug(f"PostgreSQL connection failed ({e}), enabling in-memory fallback.")
            raise
    return _pool


@asynccontextmanager
async def db_connection() -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy[asyncpg.Record], None]:
    """Context manager for borrowing a connection from the pool."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        yield conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS indexed_files (
    id BIGSERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    blob_hash VARCHAR(64) NOT NULL,
    commit_sha VARCHAR(64),
    language VARCHAR(50),
    size_bytes BIGINT NOT NULL,
    mtime DOUBLE PRECISION,
    indexed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_repo_file UNIQUE (repo_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_indexed_files_repo ON indexed_files(repo_id);
CREATE INDEX IF NOT EXISTS idx_indexed_files_hash ON indexed_files(blob_hash);
"""


class ManifestStore:
    """PostgreSQL storage manager for repository manifest records with in-memory fallback."""

    _manifest_cache: dict[str, dict[str, tuple[str, float | None]]] = {}
    _commit_cache: dict[str, str | None] = {}

    @staticmethod
    async def init_schema() -> None:
        """Executes DDL migrations to ensure the indexed_files table exists."""
        try:
            async with db_connection() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("Manifest database schema verified.")
        except Exception as e:
            logger.warning(f"Could not initialize manifest schema (DB might be offline): {e}")

    @classmethod
    async def get_last_indexed_commit(cls, repo_id: str) -> str | None:
        """Returns the most recent commit SHA recorded for this repo."""
        query = """
            SELECT commit_sha FROM indexed_files
            WHERE repo_id = $1 AND commit_sha IS NOT NULL
            ORDER BY indexed_at DESC LIMIT 1;
        """
        try:
            async with db_connection() as conn:
                val = await conn.fetchval(query, repo_id)
                commit = str(val) if val else None
                cls._commit_cache[repo_id] = commit
                return commit
        except Exception as e:
            logger.debug(f"Failed to fetch last commit for {repo_id}: {e}")
            if repo_id not in cls._commit_cache:
                cls._commit_cache[repo_id] = load_cache(f"{repo_id}_commit")
            return cls._commit_cache.get(repo_id)

    @classmethod
    async def load_indexed_hashes(cls, repo_id: str) -> dict[str, tuple[str, float | None]]:
        """Returns { file_path: (blob_hash, mtime) } mapping for an indexed repository."""
        query = """
            SELECT file_path, blob_hash, mtime FROM indexed_files
            WHERE repo_id = $1;
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, repo_id)
                data = {row["file_path"]: (row["blob_hash"], row["mtime"]) for row in rows}
                cls._manifest_cache[repo_id] = data
                return data
        except Exception as e:
            logger.debug(f"Failed to load hashes for {repo_id}: {e}")
            if repo_id not in cls._manifest_cache or not cls._manifest_cache[repo_id]:
                disk_data = load_cache(f"{repo_id}_manifest")
                if disk_data:
                    cls._manifest_cache[repo_id] = {k: tuple(v) for k, v in disk_data.items()}
            return cls._manifest_cache.get(repo_id, {})

    @classmethod
    async def upsert_records(
        cls, records: list[ScannedFile], repo_id: str, commit_sha: str | None = None
    ) -> None:
        """Bulk upserts scanned files into the manifest table."""
        if not records:
            return

        # Always update in-memory and disk fallback
        if repo_id not in cls._manifest_cache:
            cls._manifest_cache[repo_id] = {}
        for rec in records:
            cls._manifest_cache[repo_id][rec.file_path] = (rec.blob_hash, rec.mtime)
        save_cache(f"{repo_id}_manifest", cls._manifest_cache[repo_id])
        if commit_sha:
            cls._commit_cache[repo_id] = commit_sha
            save_cache(f"{repo_id}_commit", commit_sha)

        query = """
            INSERT INTO indexed_files
                (repo_id, file_path, blob_hash, commit_sha, language, size_bytes, mtime)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (repo_id, file_path) DO UPDATE SET
                blob_hash   = EXCLUDED.blob_hash,
                commit_sha  = EXCLUDED.commit_sha,
                language    = EXCLUDED.language,
                size_bytes  = EXCLUDED.size_bytes,
                mtime       = EXCLUDED.mtime,
                indexed_at  = CURRENT_TIMESTAMP;
        """
        data = [
            (
                repo_id,
                rec.file_path,
                rec.blob_hash,
                commit_sha,
                rec.language,
                rec.size_bytes,
                rec.mtime,
            )
            for rec in records
        ]
        try:
            async with db_connection() as conn:
                await conn.executemany(query, data)
            logger.info(f"Manifest: Upserted {len(records)} records for repo {repo_id}")
        except Exception as e:
            logger.debug(f"Failed to upsert manifest records into DB (using cache): {e}")

    @classmethod
    async def delete_records(cls, file_paths: list[str], repo_id: str) -> None:
        """Removes manifest records for deleted files."""
        if not file_paths:
            return
        if repo_id in cls._manifest_cache:
            for p in file_paths:
                cls._manifest_cache[repo_id].pop(p, None)

        query = """
            DELETE FROM indexed_files
            WHERE repo_id = $1 AND file_path = ANY($2::text[]);
        """
        try:
            async with db_connection() as conn:
                await conn.execute(query, repo_id, file_paths)
            logger.info(f"Manifest: Deleted {len(file_paths)} records for repo {repo_id}")
        except Exception as e:
            logger.debug(f"Failed to delete manifest records from DB (using cache): {e}")
