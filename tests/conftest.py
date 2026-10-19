"""Pytest fixtures and configuration."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def async_client() -> AsyncClient:
    """Asynchronous test client for FastAPI endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
