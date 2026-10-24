"""Unit tests for repository lifecycle, graph explorer, and file inspection endpoints."""

import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.api.job_store import JobStore
from src.parser.graph_store import CodeGraphStore
from src.parser.models import CodeEdge, CodeSymbol, EdgeType, SymbolKind


@pytest.mark.asyncio
async def test_init_repo_endpoint(async_client: AsyncClient) -> None:
    """Tests POST /api/repos/init schedules a background job and returns 202 Accepted."""
    payload = {
        "repo_id": "test-sample-service",
        "source_type": "local",
        "source_path": os.getcwd(),
    }
    with patch("src.api.job_manager.JobManager._run_indexing_pipeline"):
        response = await async_client.post("/api/repos/init", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["repo_id"] == "test-sample-service"
        assert data["status"] == "queued"
        assert "job_id" in data


@pytest.mark.asyncio
async def test_list_repos_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/repos returns collection of repositories."""
    # Ensure at least one repo exists in JobStore
    await JobStore.create_job(job_id="dummy-repo-job", repo_id="dummy-repo-1")

    response = await async_client.get("/api/repos")
    assert response.status_code == 200
    data = response.json()
    assert "repositories" in data
    assert isinstance(data["repositories"], list)
    assert any(r["repo_id"] == "dummy-repo-1" for r in data["repositories"])


@pytest.mark.asyncio
async def test_get_repo_map_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/repos/{repo_id}/map returns structural map outline."""
    # Seed symbols
    sym = CodeSymbol(
        file_path="src/service.py",
        name="AuthService",
        qualified_name="src.service.AuthService",
        kind=SymbolKind.CLASS,
        signature="class AuthService",
        start_line=1,
        end_line=20,
        language="python",
    )
    await CodeGraphStore.upsert_symbols([sym], repo_id="sample-map-repo")

    response = await async_client.get("/api/repos/sample-map-repo/map")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "sample-map-repo"
    assert "AuthService" in data["repo_map"]


@pytest.mark.asyncio
async def test_get_repo_graph_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/repos/{repo_id}/graph returns nodes and edges."""
    sym = CodeSymbol(
        file_path="src/main.py",
        name="bootstrap",
        qualified_name="src.main.bootstrap",
        kind=SymbolKind.FUNCTION,
        signature="def bootstrap()",
        start_line=5,
        end_line=15,
        language="python",
        centrality_score=0.9,
    )
    edge = CodeEdge(
        source_symbol="bootstrap",
        target_symbol="init_db",
        edge_type=EdgeType.CALLS,
        source_file="src/main.py",
        target_file="src/db.py",
    )
    await CodeGraphStore.upsert_symbols([sym], repo_id="sample-graph-repo")
    await CodeGraphStore.upsert_edges([edge], repo_id="sample-graph-repo")

    response = await async_client.get("/api/repos/sample-graph-repo/graph")
    assert response.status_code == 200
    data = response.json()
    assert data["repo_id"] == "sample-graph-repo"
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_get_file_content_endpoint(async_client: AsyncClient) -> None:
    """Tests GET /api/repos/{repo_id}/file reads and numbers lines safely."""
    # Read README.md in current directory
    response = await async_client.get(
        "/api/repos/Agentic-Code-RAG/file",
        params={"file_path": "README.md", "start_line": 1, "end_line": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_path"] == "README.md"
    assert data["start_line"] == 1
    assert "1 | #" in data["content"]


@pytest.mark.asyncio
async def test_delete_repo_endpoint(async_client: AsyncClient) -> None:
    """Tests DELETE /api/repos/{repo_id} cascading delete."""
    await JobStore.create_job(job_id="purge-job-01", repo_id="purge-repo")

    response = await async_client.delete("/api/repos/purge-repo")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert data["repo_id"] == "purge-repo"
    assert "purged_records" in data
