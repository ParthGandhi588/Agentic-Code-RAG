"""Unit tests for LangGraph AgentState and conditional routing functions."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages

from src.agent.graph import post_crag_routing, post_tools_routing, should_continue
from src.agent.state import AgentState


def test_agent_state_message_reducer() -> None:
    """Verifies that add_messages properly appends messages to state."""
    initial: list[HumanMessage | AIMessage] = [HumanMessage(content="Hello")]
    new_message = AIMessage(content="Hi there!")
    reduced = add_messages(initial, [new_message])

    assert len(reduced) == 2
    assert reduced[0].content == "Hello"
    assert reduced[1].content == "Hi there!"


def test_should_continue_routing() -> None:
    """Verifies agent routing between tools and answer synthesis."""
    # Case 1: Max iterations reached -> answer_node
    state_max: AgentState = {
        "messages": [HumanMessage(content="Query")],
        "repo_id": "test_repo",
        "repo_map_summary": "",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 8,
        "max_iterations": 8,
        "final_answer": None,
        "error": None,
    }
    assert should_continue(state_max) == "answer_node"

    # Case 2: Tool call present -> tools
    ai_with_tool = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "hybrid_code_search",
                "args": {"query": "test"},
                "id": "tc1",
                "type": "tool_call",
            }
        ],
    )
    state_tool: AgentState = {
        "messages": [HumanMessage(content="Query"), ai_with_tool],
        "repo_id": "test_repo",
        "repo_map_summary": "",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 1,
        "max_iterations": 8,
        "final_answer": None,
        "error": None,
    }
    assert should_continue(state_tool) == "tools"

    # Case 3: No tool calls -> answer_node
    ai_no_tool = AIMessage(content="I have the answer.")
    state_direct: AgentState = {
        "messages": [HumanMessage(content="Query"), ai_no_tool],
        "repo_id": "test_repo",
        "repo_map_summary": "",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 1,
        "max_iterations": 8,
        "final_answer": None,
        "error": None,
    }
    assert should_continue(state_direct) == "answer_node"


def test_post_tools_and_crag_routing() -> None:
    """Verifies conditional routing following tool execution and CRAG grading."""
    # Post tools routing with search tool -> crag_evaluator
    ai_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "hybrid_code_search",
                "args": {"query": "auth"},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    tool_resp = ToolMessage(content="auth code snippet", tool_call_id="c1")
    state_tools: AgentState = {
        "messages": [ai_call, tool_resp],
        "repo_id": "test_repo",
        "repo_map_summary": "",
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 1,
        "max_iterations": 8,
        "final_answer": None,
        "error": None,
    }
    assert post_tools_routing(state_tools) == "crag_evaluator"

    # Post CRAG routing: insufficient -> back to agent
    state_insufficient: AgentState = {**state_tools, "crag_status": "insufficient", "iteration": 2}
    assert post_crag_routing(state_insufficient) == "agent"

    # Post CRAG routing: relevant -> answer_node
    state_relevant: AgentState = {**state_tools, "crag_status": "relevant", "iteration": 2}
    assert post_crag_routing(state_relevant) == "answer_node"
