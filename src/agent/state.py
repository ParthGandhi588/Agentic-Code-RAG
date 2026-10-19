"""Typed State definition for the LangGraph Autonomous Code-RAG Agent."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

CRAGStatus = Literal["pending", "relevant", "insufficient", "irrelevant"]


class AgentState(TypedDict):
    """Execution state tracked across the LangGraph state machine.

    Attributes:
        messages: Chat history, tool call requests, and tool execution outputs.
        repo_id: Unique repository identifier.
        repo_map_summary: Structural PageRank ASCII overview of the codebase.
        discovered_symbols: Set or list of AST symbols identified during analysis.
        retrieved_chunks: Raw code chunks returned by hybrid search or symbol lookup.
        inspected_snippets: Cache of exact line ranges read via read_file_range.
        crag_status: Corrective RAG evaluation outcome.
        iteration: Current reasoning loop counter.
        max_iterations: Maximum allowed reasoning steps before forcing synthesis.
        final_answer: Grounded final response synthesized for the user.
        error: Detailed error message if a failure occurred.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    repo_id: str
    repo_map_summary: str
    discovered_symbols: list[str]
    retrieved_chunks: list[dict[str, Any]]
    inspected_snippets: dict[str, str]
    crag_status: CRAGStatus
    iteration: int
    max_iterations: int
    final_answer: str | None
    error: str | None
