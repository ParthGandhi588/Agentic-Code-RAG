"""LangGraph StateGraph assembly, routing logic, and compilation for Codebase RAG."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agent.nodes import AgentNodes
from src.agent.state import AgentState
from src.agent.tools.tools import ALL_AGENT_TOOLS
from src.core.logger import setup_logger

logger = setup_logger("agentic-graph")


def should_continue(state: AgentState) -> Literal["tools", "answer_node"]:
    """Conditional edge from agent node deciding whether to execute tools or synthesize."""
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 8)

    if iteration >= max_iter:
        logger.info(
            f"Agent reached max iterations ({iteration}/{max_iter}). Routing to answer_node."
        )
        return "answer_node"

    messages = state.get("messages", [])
    if not messages:
        return "answer_node"

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)

    if tool_calls and len(tool_calls) > 0:
        return "tools"

    return "answer_node"


def post_tools_routing(state: AgentState) -> Literal["crag_evaluator", "agent"]:
    """Routes after tool execution: directs search/symbol retrieval to CRAG grading, others back to agent."""
    messages = state.get("messages", [])
    # Check the second-to-last message (AIMessage that issued the tool calls)
    for m in reversed(messages):
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name", "")
                if name in ("hybrid_code_search", "find_symbol_definitions"):
                    return "crag_evaluator"
            break
    return "agent"


def post_crag_routing(state: AgentState) -> Literal["agent", "answer_node"]:
    """Routes after CRAG evaluation: loops back to agent for refinement or proceeds to final answer."""
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 8)

    if iteration >= max_iter:
        return "answer_node"

    status = state.get("crag_status", "relevant")
    if status in ("insufficient", "irrelevant"):
        return "agent"

    return "answer_node"


def build_code_rag_graph(
    llm: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph:
    """Constructs and compiles the full LangGraph state machine.

    Args:
        llm: The underlying chat model with tool calling capabilities.
        checkpointer: State checkpointer for durable session persistence (defaults to in-memory).

    Returns:
        CompiledStateGraph ready for execution or event streaming.
    """
    # Bind tools to the model
    llm_with_tools = llm.bind_tools(ALL_AGENT_TOOLS)
    nodes = AgentNodes(llm=llm_with_tools)

    workflow = StateGraph(AgentState)

    # 1. Register Nodes
    workflow.add_node("agent", nodes.agent_node)
    workflow.add_node("tools", ToolNode(ALL_AGENT_TOOLS))
    workflow.add_node("crag_evaluator", nodes.crag_evaluator_node)
    workflow.add_node("answer_node", nodes.answer_node)

    # 2. Add Edges & Conditional Routing
    workflow.add_edge(START, "agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "answer_node": "answer_node",
        },
    )

    workflow.add_conditional_edges(
        "tools",
        post_tools_routing,
        {
            "crag_evaluator": "crag_evaluator",
            "agent": "agent",
        },
    )

    workflow.add_conditional_edges(
        "crag_evaluator",
        post_crag_routing,
        {
            "agent": "agent",
            "answer_node": "answer_node",
        },
    )

    workflow.add_edge("answer_node", END)

    saver = checkpointer or MemorySaver()
    compiled: CompiledStateGraph = workflow.compile(checkpointer=saver)
    logger.info("Codebase RAG LangGraph state machine compiled successfully.")
    return compiled
