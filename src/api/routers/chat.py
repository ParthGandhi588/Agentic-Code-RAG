"""API router for interactive agent reasoning and real-time SSE token streaming."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from src.agent.factory import create_agent, stream_agent_events
from src.api.schemas import ChatRequest
from src.core.logger import setup_logger
from src.parser.graph_store import CodeGraphStore

router = APIRouter(prefix="/api/chat", tags=["Agent Chat"])
logger = setup_logger("agentic-chat-api")

# Cached agent instance
_agent_instance: CompiledStateGraph | None = None


def get_agent() -> CompiledStateGraph:
    """Lazily initializes and caches the compiled LangGraph agent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = create_agent()
    return _agent_instance


@router.post(
    "",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with Autonomous Agent (SSE)",
    description="Streams multi-hop agent reasoning steps, tool execution events, and LLM text tokens in real time via Server-Sent Events.",
)
async def chat_with_agent(payload: ChatRequest) -> StreamingResponse:
    """Invokes the LangGraph agent state machine and streams events via SSE."""
    repo_id = payload.repo_id
    query = payload.message
    thread_id = payload.thread_id or f"thread_{repo_id}_{uuid.uuid4().hex[:8]}"

    # Verify repository has indexed symbols or files
    symbols = await CodeGraphStore.find_symbol_definitions(symbol_name="%", repo_id=repo_id)
    repo_map_summary = ""
    if symbols:
        top_symbols = [f"{s.kind.value}: {s.name} in {s.file_path}" for s in symbols[:40]]
        repo_map_summary = f"Identified {len(symbols)} symbols. Top symbols:\n" + "\n".join(
            top_symbols
        )

    async def sse_event_stream() -> AsyncGenerator[str, None]:
        try:
            try:
                agent = get_agent()
            except Exception as e:
                err_msg = (
                    f"LLM initialization failed: {e}. "
                    "Please set your GOOGLE_API_KEY, GROQ_API_KEY, or run local Ollama in your environment or .env file."
                )
                logger.error(err_msg)
                yield f"event: error\ndata: {json.dumps({'error': err_msg, 'thread_id': thread_id})}\n\n"
                return

            logger.info(f"Initiating agent reasoning for repo '{repo_id}' on thread '{thread_id}'.")
            async for ev in stream_agent_events(
                agent=agent,
                repo_id=repo_id,
                query=query,
                thread_id=thread_id,
                repo_map_summary=repo_map_summary,
            ):
                event_type = ev.get("event", "message")
                data_payload = json.dumps(ev)
                yield f"event: {event_type}\ndata: {data_payload}\n\n"

            # Emit final completion signal
            done_payload = json.dumps({"status": "completed", "thread_id": thread_id})
            yield f"event: done\ndata: {done_payload}\n\n"

        except Exception as e:
            logger.error(f"Agent execution stream failed: {e}", exc_info=True)
            err_payload = json.dumps({"error": str(e), "thread_id": thread_id})
            yield f"event: error\ndata: {err_payload}\n\n"

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
