"""API router for querying indexing jobs and streaming live SSE progress."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from src.api.errors import JobNotFoundError
from src.api.job_manager import JobManager
from src.api.job_store import JobStore
from src.api.schemas import IndexingJobResponse

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get(
    "/{job_id}",
    response_model=IndexingJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Indexing Job Status",
    description="Retrieve the current status, progress percentage, and telemetry logs of an indexing job.",
)
async def get_job_status(job_id: str) -> IndexingJobResponse:
    """Returns the current state of an indexing job."""
    job = await JobStore.get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return job


@router.get(
    "/{job_id}/stream",
    response_class=StreamingResponse,
    summary="Stream Indexing Job Telemetry (SSE)",
    description="Live Server-Sent Events stream emitting progress percentage, phase transitions, and logs.",
)
async def stream_job_telemetry(job_id: str) -> StreamingResponse:
    """Streams Server-Sent Events (SSE) representing live progress transitions."""
    # Verify job exists first
    job = await JobStore.get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for update in JobManager.subscribe(job_id):
            payload = json.dumps(update.model_dump(mode="json"))
            yield f"event: progress\ndata: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
