"""Durable PostgreSQL and in-memory storage manager for repository indexing jobs."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from src.api.schemas import IndexingJobResponse, JobStatus
from src.core.logger import setup_logger
from src.ingest.manifest import db_connection

logger = setup_logger("agentic-job-store")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS indexing_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    progress_pct INTEGER DEFAULT 0,
    current_phase VARCHAR(100) DEFAULT 'queued',
    telemetry_logs JSONB DEFAULT '[]'::jsonb,
    error_msg TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_repo ON indexing_jobs(repo_id);
CREATE INDEX IF NOT EXISTS idx_indexing_jobs_status ON indexing_jobs(status);
"""


class JobStore:
    """Manages transactional persistence for indexing jobs with in-memory fallback cache."""

    # In-memory fast cache ensuring resilience during DB reconnects and tests
    _memory_cache: dict[str, IndexingJobResponse] = {}

    @classmethod
    async def init_schema(cls) -> None:
        """Initializes the indexing_jobs table in PostgreSQL."""
        try:
            async with db_connection() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("Indexing jobs database schema verified.")
        except Exception as e:
            logger.warning(
                f"Could not initialize indexing_jobs schema (running in memory fallback): {e}"
            )

    @classmethod
    async def create_job(cls, job_id: str, repo_id: str) -> IndexingJobResponse:
        """Creates and persists a new indexing job in QUEUED status."""
        now = datetime.now(UTC)
        job = IndexingJobResponse(
            job_id=job_id,
            repo_id=repo_id,
            status=JobStatus.QUEUED,
            progress_pct=0,
            current_phase="queued",
            telemetry_logs=[f"Job {job_id} queued for repository '{repo_id}'."],
            error_msg=None,
            created_at=now,
            updated_at=now,
        )
        cls._memory_cache[job_id] = job

        try:
            async with db_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO indexing_jobs
                    (job_id, repo_id, status, progress_pct, current_phase, telemetry_logs, error_msg, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (job_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        progress_pct = EXCLUDED.progress_pct,
                        current_phase = EXCLUDED.current_phase,
                        telemetry_logs = EXCLUDED.telemetry_logs,
                        updated_at = EXCLUDED.updated_at
                    """,
                    job.job_id,
                    job.repo_id,
                    job.status.value,
                    job.progress_pct,
                    job.current_phase,
                    json.dumps(job.telemetry_logs),
                    job.error_msg,
                    job.created_at,
                    job.updated_at,
                )
        except Exception as e:
            logger.debug(f"DB insert failed for job {job_id}, cached in memory: {e}")

        return job

    @classmethod
    async def update_progress(
        cls,
        job_id: str,
        status: JobStatus,
        progress_pct: int,
        phase: str,
        log_message: str | None = None,
        error_msg: str | None = None,
    ) -> IndexingJobResponse | None:
        """Updates progress, phase, and telemetry logs for a running job."""
        job = cls._memory_cache.get(job_id)
        now = datetime.now(UTC)

        if job is None:
            job = await cls.get_job(job_id)
            if job is None:
                return None

        # Mutate job record
        job.status = status
        job.progress_pct = max(0, min(100, progress_pct))
        job.current_phase = phase
        job.updated_at = now
        if log_message:
            job.telemetry_logs.append(f"[{phase.upper()}] {log_message}")
        if error_msg:
            job.error_msg = error_msg

        cls._memory_cache[job_id] = job

        try:
            async with db_connection() as conn:
                await conn.execute(
                    """
                    UPDATE indexing_jobs
                    SET status = $2, progress_pct = $3, current_phase = $4,
                        telemetry_logs = $5, error_msg = $6, updated_at = $7
                    WHERE job_id = $1
                    """,
                    job_id,
                    job.status.value,
                    job.progress_pct,
                    job.current_phase,
                    json.dumps(job.telemetry_logs),
                    job.error_msg,
                    now,
                )
        except Exception as e:
            logger.debug(f"DB update failed for job {job_id}: {e}")

        return job

    @classmethod
    async def get_job(cls, job_id: str) -> IndexingJobResponse | None:
        """Fetches job metadata from the database or in-memory fallback cache."""
        if job_id in cls._memory_cache:
            return cls._memory_cache[job_id]

        try:
            async with db_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT job_id, repo_id, status, progress_pct, current_phase,
                           telemetry_logs, error_msg, created_at, updated_at
                    FROM indexing_jobs
                    WHERE job_id = $1
                    """,
                    job_id,
                )
                if row:
                    raw_logs = row["telemetry_logs"]
                    logs: list[str] = (
                        json.loads(raw_logs)
                        if isinstance(raw_logs, str)
                        else (list(raw_logs) if raw_logs else [])
                    )
                    job = IndexingJobResponse(
                        job_id=row["job_id"],
                        repo_id=row["repo_id"],
                        status=JobStatus(row["status"]),
                        progress_pct=row["progress_pct"],
                        current_phase=row["current_phase"],
                        telemetry_logs=logs,
                        error_msg=row["error_msg"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    cls._memory_cache[job_id] = job
                    return job
        except Exception as e:
            logger.debug(f"DB read failed for job {job_id}: {e}")

        return None

    @classmethod
    async def list_jobs_for_repo(cls, repo_id: str) -> list[IndexingJobResponse]:
        """Returns all indexing jobs associated with a repository."""
        jobs: list[IndexingJobResponse] = []
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT job_id, repo_id, status, progress_pct, current_phase,
                           telemetry_logs, error_msg, created_at, updated_at
                    FROM indexing_jobs
                    WHERE repo_id = $1
                    ORDER BY created_at DESC
                    """,
                    repo_id,
                )
                for row in rows:
                    raw_logs = row["telemetry_logs"]
                    logs = (
                        json.loads(raw_logs) if isinstance(raw_logs, str) else list(raw_logs or [])
                    )
                    jobs.append(
                        IndexingJobResponse(
                            job_id=row["job_id"],
                            repo_id=row["repo_id"],
                            status=JobStatus(row["status"]),
                            progress_pct=row["progress_pct"],
                            current_phase=row["current_phase"],
                            telemetry_logs=logs,
                            error_msg=row["error_msg"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
                    )
                return jobs
        except Exception as e:
            logger.debug(f"DB list_jobs_for_repo failed: {e}")

        # Fallback to in-memory cache
        return [j for j in cls._memory_cache.values() if j.repo_id == repo_id]

    @classmethod
    async def delete_jobs_for_repo(cls, repo_id: str) -> int:
        """Deletes all job records associated with a repository."""
        deleted = 0
        try:
            async with db_connection() as conn:
                res = await conn.execute("DELETE FROM indexing_jobs WHERE repo_id = $1", repo_id)
                # res format: 'DELETE <count>'
                parts = res.split()
                if len(parts) == 2:
                    deleted = int(parts[1])
        except Exception as e:
            logger.debug(f"DB delete_jobs_for_repo failed: {e}")

        # Purge from memory cache
        for jid in list(cls._memory_cache.keys()):
            if cls._memory_cache[jid].repo_id == repo_id:
                del cls._memory_cache[jid]
                deleted += 1

        return deleted
