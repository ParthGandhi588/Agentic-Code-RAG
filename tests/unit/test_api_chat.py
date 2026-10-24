"""Unit tests for the real-time SSE Agent Chat API endpoint."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient


async def mock_stream_agent_events(
    agent: Any,
    repo_id: str,
    query: str,
    thread_id: str = "default_thread",
    repo_map_summary: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    """Mock generator yielding simulated agent reasoning events."""
    yield {
        "event": "tool_start",
        "tool": "inspect_repo_map",
        "input": {"repo_id": repo_id},
    }
    yield {
        "event": "tool_end",
        "tool": "inspect_repo_map",
        "output_preview": "# Topology Overview: 15 symbols identified",
    }
    yield {
        "event": "token",
        "content": "The repository uses FastAPI as its API framework.",
    }


@pytest.mark.asyncio
async def test_chat_sse_stream_endpoint(async_client: AsyncClient) -> None:
    """Tests POST /api/chat streams SSE events (tool_start, tool_end, token, done)."""
    with (
        patch("src.api.routers.chat.get_agent", return_value=object()),
        patch(
            "src.api.routers.chat.stream_agent_events",
            side_effect=mock_stream_agent_events,
        ),
    ):
        payload = {
            "repo_id": "test-chat-repo",
            "message": "How does the entrypoint work?",
            "thread_id": "test-session-123",
        }

        async with async_client.stream("POST", "/api/chat", json=payload) as stream:
            assert stream.status_code == 200
            assert "text/event-stream" in stream.headers.get("content-type", "")

            raw_events = []
            async for line in stream.aiter_lines():
                if line.strip():
                    raw_events.append(line.strip())

            event_text = "\n".join(raw_events)
            assert "event: tool_start" in event_text
            assert "inspect_repo_map" in event_text
            assert "event: tool_end" in event_text
            assert "event: token" in event_text
            assert "FastAPI" in event_text
            assert "event: done" in event_text
