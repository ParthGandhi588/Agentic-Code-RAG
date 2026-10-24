"""Unit tests for REST API Pydantic v2 schemas and validation constraints."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    FileContentResponse,
    GraphEdge,
    GraphNode,
    IndexingJobResponse,
    JobStatus,
    RepoInitRequest,
)


def test_repo_init_request_validation() -> None:
    """Tests valid repo_id patterns and invalid character rejection."""
    valid = RepoInitRequest(
        repo_id="my-service_v2.0",
        source_type="local",
        source_path="/valid/path",
    )
    assert valid.repo_id == "my-service_v2.0"
    assert valid.source_type == "local"

    # Reject invalid characters (e.g. spaces, slashes)
    with pytest.raises(ValidationError):
        RepoInitRequest(
            repo_id="invalid repo id with spaces",
            source_path="/path",
        )

    with pytest.raises(ValidationError):
        RepoInitRequest(
            repo_id="invalid/slash",
            source_path="/path",
        )


def test_indexing_job_response_schema() -> None:
    """Tests IndexingJobResponse serialization and percentage validation."""
    now = datetime.now(UTC)
    job = IndexingJobResponse(
        job_id="job-123",
        repo_id="test-repo",
        status=JobStatus.AST_PARSING,
        progress_pct=60,
        current_phase="ast_parsing",
        telemetry_logs=["Started AST parsing"],
        error_msg=None,
        created_at=now,
        updated_at=now,
    )
    assert job.progress_pct == 60
    assert job.status == JobStatus.AST_PARSING

    # Reject progress > 100
    with pytest.raises(ValidationError):
        IndexingJobResponse(
            job_id="job-123",
            repo_id="test-repo",
            status=JobStatus.INDEXING,
            progress_pct=150,
            current_phase="indexing",
            created_at=now,
            updated_at=now,
        )


def test_graph_and_file_response_schemas() -> None:
    """Tests GraphNode, GraphEdge, and FileContentResponse schemas."""
    node = GraphNode(
        id="app.py:main",
        name="main",
        kind="function",
        file_path="app.py",
        line=10,
        pagerank_score=0.42,
    )
    assert node.pagerank_score == 0.42

    edge = GraphEdge(source="app.py:main", target="db.py:connect", edge_type="calls")
    assert edge.edge_type == "calls"

    file_resp = FileContentResponse(
        repo_id="test-repo",
        file_path="app.py",
        total_lines=50,
        start_line=1,
        end_line=20,
        content="   1 | def main(): pass",
    )
    assert file_resp.total_lines == 50
    assert "def main():" in file_resp.content
