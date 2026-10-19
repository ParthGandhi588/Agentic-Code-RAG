"""Unit tests for compiling and executing the LangGraph agent state machine."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool

from src.agent.factory import stream_agent_events
from src.agent.graph import build_code_rag_graph
from src.agent.state import AgentState


class MockToolChatModel(BaseChatModel):
    """Custom mock chat model that implements bind_tools and emits sequential messages."""

    responses: list[AIMessage]
    current_idx: int = 0

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        resp = self.responses[min(self.current_idx, len(self.responses) - 1)]
        self.current_idx += 1
        return ChatResult(generations=[ChatGeneration(message=resp)])

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "mock-tool-chat"


@pytest.mark.asyncio
async def test_agent_graph_direct_answer() -> None:
    """Verifies that an agent producing no tool calls routes straight to synthesis and terminates."""
    fake_llm = MockToolChatModel(
        responses=[
            AIMessage(content="Direct answer: The project uses FastAPI and PostgreSQL."),
            AIMessage(content="Synthesized final answer with verified details."),
        ]
    )

    graph = build_code_rag_graph(llm=fake_llm)

    initial_state: AgentState = {
        "messages": [HumanMessage(content="What framework is used?")],
        "repo_id": "test_repo",
        "repo_map_summary": "# Repo Map",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 0,
        "max_iterations": 5,
        "final_answer": None,
        "error": None,
    }

    result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": "t1"}})
    assert result["final_answer"] is not None
    assert "Synthesized final answer" in result["final_answer"]
    assert result["iteration"] >= 1


@pytest.mark.asyncio
async def test_agent_graph_tool_execution_loop(tmp_path: Path) -> None:
    """Verifies state machine traversal: agent -> tools -> crag_evaluator -> answer_node."""
    sample_file = tmp_path / "config.py"
    sample_file.write_text("class Settings:\n    app_port = 8000\n")

    # Step 1: Agent calls read_file_range
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "read_file_range",
                "args": {
                    "repo_id": "test_repo",
                    "file_path": str(sample_file),
                    "start_line": 1,
                    "end_line": 5,
                },
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    # Step 2: Agent synthesizes final answer
    synthesis_msg = AIMessage(content="Verified in config.py: app_port is 8000.")

    fake_llm = MockToolChatModel(responses=[tool_call_msg, synthesis_msg, synthesis_msg])
    graph = build_code_rag_graph(llm=fake_llm)

    initial_state: AgentState = {
        "messages": [HumanMessage(content="What is the port?")],
        "repo_id": "test_repo",
        "repo_map_summary": "",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 0,
        "max_iterations": 5,
        "final_answer": None,
        "error": None,
    }

    result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": "t2"}})
    assert result["final_answer"] is not None
    assert "app_port is 8000" in result["final_answer"]

    # Verify that a ToolMessage was generated during execution
    messages = result["messages"]
    tool_messages = [m for m in messages if getattr(m, "type", "") == "tool"]
    assert len(tool_messages) >= 1
    assert "Lines 1-2 of 2" in str(tool_messages[0].content)


@pytest.mark.asyncio
async def test_stream_agent_events_generation() -> None:
    """Verifies that stream_agent_events yields structured events without error."""
    mock_agent = AsyncMock()

    async def mock_events(*args: Any, **kwargs: Any):
        yield {
            "event": "on_tool_start",
            "name": "inspect_repo_map",
            "data": {"input": {"repo_id": "demo"}},
        }
        yield {
            "event": "on_tool_end",
            "name": "inspect_repo_map",
            "data": {"output": "# Repo map content"},
        }

    mock_agent.astream_events = mock_events

    events: list[dict[str, Any]] = []
    async for ev in stream_agent_events(mock_agent, repo_id="demo", query="list files"):
        events.append(ev)

    assert len(events) == 2
    assert events[0]["event"] == "tool_start"
    assert events[0]["tool"] == "inspect_repo_map"
    assert events[1]["event"] == "tool_end"
