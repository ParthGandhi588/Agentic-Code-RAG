"""Unit tests for RFC 7807 Problem Details error translation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_validation_error_rfc7807(async_client: AsyncClient) -> None:
    """Tests that payload validation failures return RFC 7807 application/problem+json."""
    # Send empty payload violating required fields
    response = await async_client.post("/api/repos/init", json={})
    assert response.status_code == 422
    assert "application/problem+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["type"] == "urn:agentic:error:validation-error"
    assert data["title"] == "Request Validation Failed"
    assert data["status"] == 422
    assert isinstance(data.get("invalid_params"), list)
    assert len(data["invalid_params"]) > 0


@pytest.mark.asyncio
async def test_job_not_found_rfc7807(async_client: AsyncClient) -> None:
    """Tests 404 response for nonexistent job returns Problem Details."""
    response = await async_client.get("/api/jobs/nonexistent-job-uuid")
    assert response.status_code == 404
    assert "application/problem+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["type"] == "urn:agentic:error:job-not-found"
    assert data["title"] == "Indexing Job Not Found"
    assert "nonexistent-job-uuid" in data["detail"]


@pytest.mark.asyncio
async def test_path_traversal_forbidden_rfc7807(async_client: AsyncClient) -> None:
    """Tests that path traversal attempts return 403 Forbidden with RFC 7807 problem details."""
    response = await async_client.get(
        "/api/repos/test-repo/file",
        params={"file_path": "../../etc/passwd"},
    )
    assert response.status_code == 403
    assert "application/problem+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["type"] == "urn:agentic:error:path-traversal"
    assert data["title"] == "Access Denied: Path Traversal"
    assert data["status"] == 403
