"""Unit tests for JobStore and jobs REST / SSE streaming endpoints."""

import asyncio

import pytest
from httpx import AsyncClient

from src.api.job_manager import JobManager
from src.api.job_store import JobStore
from src.api.schemas import JobStatus


@pytest.mark.asyncio
async def test_job_store_lifecycle() -> None:
    """Tests job creation, progress updates, retrieval, and cascading deletion."""
    job_id = "test-job-store-001"
    repo_id = "test-store-repo"

    # 1. Create Job
    job = await JobStore.create_job(job_id=job_id, repo_id=repo_id)
    assert job.job_id == job_id
    assert job.status == JobStatus.QUEUED
    assert job.progress_pct == 0

    # 2. Update Progress
    updated = await JobStore.update_progress(
        job_id=job_id,
        status=JobStatus.AST_PARSING,
        progress_pct=55,
        phase="ast_parsing",
        log_message="Extracted 42 symbols",
    )
    assert updated is not None
    assert updated.status == JobStatus.AST_PARSING
    assert updated.progress_pct == 55
    assert any("Extracted 42 symbols" in log for log in updated.telemetry_logs)

    # 3. Retrieve Job
    fetched = await JobStore.get_job(job_id)
    assert fetched is not None
    assert fetched.progress_pct == 55

    # 4. List for Repo
    jobs = await JobStore.list_jobs_for_repo(repo_id)
    assert len(jobs) >= 1
    assert any(j.job_id == job_id for j in jobs)

    # 5. Delete Jobs for Repo
    deleted_count = await JobStore.delete_jobs_for_repo(repo_id)
    assert deleted_count >= 1
    assert await JobStore.get_job(job_id) is None


@pytest.mark.asyncio
async def test_get_job_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/jobs/{job_id} endpoint."""
    await JobStore.create_job(job_id="endpoint-job-001", repo_id="endpoint-repo")
    await JobStore.update_progress(
        job_id="endpoint-job-001",
        status=JobStatus.INDEXING,
        progress_pct=80,
        phase="indexing",
    )

    response = await async_client.get("/api/jobs/endpoint-job-001")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "endpoint-job-001"
    assert data["status"] == "indexing"
    assert data["progress_pct"] == 80


@pytest.mark.asyncio
async def test_stream_job_sse_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/jobs/{job_id}/stream SSE telemetry stream."""
    job_id = "stream-job-001"
    await JobStore.create_job(job_id=job_id, repo_id="stream-repo")

    async def emit_completion() -> None:
        await asyncio.sleep(0.05)
        await JobManager._emit_progress(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress_pct=100,
            phase="completed",
            log_message="Indexing finished.",
        )

    asyncio.create_task(emit_completion())

    # Read SSE stream
    async with async_client.stream("GET", f"/api/jobs/{job_id}/stream") as stream:
        assert stream.status_code == 200
        assert "text/event-stream" in stream.headers.get("content-type", "")

        events = []
        async for line in stream.aiter_lines():
            if line.startswith("event:") or line.startswith("data:"):
                events.append(line)
            if len(events) >= 4:
                break

        assert any("event: progress" in e for e in events)
        assert any("stream-job-001" in e for e in events)
