"""Type-safe Pydantic v2 schemas for Agentic-Code-RAG REST API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """Lifecycle statuses for asynchronous repository indexing jobs."""

    QUEUED = "queued"
    CLONING = "cloning"
    SCANNING = "scanning"
    AST_PARSING = "ast_parsing"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


# -----------------------------------------------------------------------------
# Repository Ingestion Schemas
# -----------------------------------------------------------------------------


class RepoInitRequest(BaseModel):
    """Payload to initiate repository indexing."""

    repo_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
        description="Unique identifier for the repository (alphanumeric, dashes, underscores, dots).",
        examples=["agentic-code-rag"],
    )
    source_type: str = Field(
        default="local",
        description="Source type: 'local' for filesystem path or 'git' for remote URL.",
    )
    source_path: str = Field(
        ...,
        min_length=1,
        description="Local directory path or remote Git repository URL (https/git).",
        examples=["/workspace/my-repo", "https://github.com/user/repo.git"],
    )
    branch: str | None = Field(
        default=None,
        description="Optional Git branch or tag to checkout for remote repositories.",
    )


class RepoInitResponse(BaseModel):
    """Response returned immediately upon scheduling an indexing job."""

    job_id: str = Field(..., description="Unique UUID tracking the indexing job.")
    repo_id: str = Field(..., description="Target repository identifier.")
    status: JobStatus = Field(default=JobStatus.QUEUED, description="Initial job status.")
    message: str = Field(..., description="Informational message regarding the scheduled job.")


class IndexingJobResponse(BaseModel):
    """Current state and progress telemetry of an indexing job."""

    job_id: str
    repo_id: str
    status: JobStatus
    progress_pct: int = Field(ge=0, le=100)
    current_phase: str
    telemetry_logs: list[str] = Field(default_factory=list)
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime


class RepoSummary(BaseModel):
    """Summary metadata of an indexed repository."""

    repo_id: str
    total_files: int
    languages: list[str]
    total_symbols: int
    last_indexed_at: datetime | None = None


class RepoListResponse(BaseModel):
    """Collection of indexed repositories."""

    repositories: list[RepoSummary]


# -----------------------------------------------------------------------------
# Graph & File Inspection Schemas
# -----------------------------------------------------------------------------


class GraphNode(BaseModel):
    """Node representing an AST symbol in the dependency explorer."""

    id: str
    name: str
    kind: str
    file_path: str
    line: int
    pagerank_score: float = 0.0


class GraphEdge(BaseModel):
    """Directed edge representing calls, imports, or inheritance between symbols."""

    source: str
    target: str
    edge_type: str


class RepoGraphResponse(BaseModel):
    """Full AST dependency and call graph for interactive visualization."""

    repo_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class FileContentResponse(BaseModel):
    """Source file contents with line range highlighting."""

    repo_id: str
    file_path: str
    total_lines: int
    start_line: int
    end_line: int
    content: str


# -----------------------------------------------------------------------------
# Chat & Agent Schemas
# -----------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Interactive reasoning request submitted to the autonomous agent."""

    repo_id: str = Field(..., min_length=1, description="Target repository to investigate.")
    message: str = Field(..., min_length=1, description="User question or exploration prompt.")
    thread_id: str | None = Field(
        default=None,
        description="Optional session/thread identifier for multi-turn conversational persistence.",
    )


class ChatEvent(BaseModel):
    """Server-Sent Event frame emitted during agent reasoning and token generation."""

    event: str = Field(
        ...,
        description="Event type: 'token', 'tool_start', 'tool_end', 'crag_eval', 'error', 'done'.",
    )
    data: dict[str, Any] = Field(default_factory=dict)
