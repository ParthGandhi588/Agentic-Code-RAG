"""LangGraph node execution functions for the Autonomous Codebase RAG agent."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agent.evaluator import CRAGEvaluator
from src.agent.prompts import AGENT_SYSTEM_PROMPT, ANSWER_SYNTHESIS_PROMPT
from src.agent.state import AgentState
from src.core.logger import setup_logger

logger = setup_logger("agentic-nodes")


class AgentNodes:
    """Encapsulates node execution logic for the LangGraph state machine."""

    def __init__(self, llm: Any, evaluator: CRAGEvaluator | None = None) -> None:
        self.llm = llm
        self.evaluator = evaluator or CRAGEvaluator(llm=llm)

    async def agent_node(self, state: AgentState) -> dict[str, Any]:
        """Core reasoning node: inspects conversation history and decides next tool or direct response."""
        messages: list[BaseMessage] = list(state.get("messages", []))
        repo_map = state.get("repo_map_summary", "")

        # Inject system prompt with live repo map context if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            system_content = AGENT_SYSTEM_PROMPT
            if repo_map:
                system_content += f"\n\n### Current Repository Map Summary:\n{repo_map}"
            messages.insert(0, SystemMessage(content=system_content))

        iteration = state.get("iteration", 0) + 1
        logger.debug(f"AgentNode: Iteration {iteration} executing.")

        response = await self.llm.ainvoke(messages)
        return {
            "messages": [response],
            "iteration": iteration,
        }

    async def crag_evaluator_node(self, state: AgentState) -> dict[str, Any]:
        """Evaluates whether the most recent retrieval tool output adequately addresses the query."""
        messages = state.get("messages", [])

        # Find user query from the first human message
        user_query = ""
        for m in messages:
            if isinstance(m, HumanMessage):
                user_query = str(m.content)
                break

        # Find the latest tool response
        latest_tool_output = ""
        for m in reversed(messages):
            if getattr(m, "type", "") == "tool" or hasattr(m, "tool_call_id"):
                latest_tool_output = str(m.content)
                break

        if not latest_tool_output:
            return {"crag_status": "relevant"}

        evaluation = await self.evaluator.aevaluate(query=user_query, context=latest_tool_output)
        logger.info(f"CRAG Evaluator: Status={evaluation.status}, Reasoning={evaluation.reasoning}")

        feedback_messages: list[BaseMessage] = []
        if evaluation.status == "insufficient":
            missing = (
                ", ".join(evaluation.missing_elements)
                if evaluation.missing_elements
                else "key symbols"
            )
            feedback_messages.append(
                SystemMessage(
                    content=f"CRAG Feedback: Retrieved code is partially relevant but lacks {missing}. "
                    "Use 'find_symbol_definitions' or 'read_file_range' to inspect missing details."
                )
            )
        elif evaluation.status == "irrelevant":
            feedback_messages.append(
                SystemMessage(
                    content="CRAG Feedback: Retrieved snippets were irrelevant or noise. "
                    "Consult the 'inspect_repo_map' or rephrase search terms."
                )
            )

        return {
            "crag_status": evaluation.status,
            "messages": feedback_messages,
        }

    async def answer_node(self, state: AgentState) -> dict[str, Any]:
        """Synthesizes the final grounded answer citing verified files, symbols, and line ranges."""
        messages = state.get("messages", [])

        user_query = ""
        context_snippets: list[str] = []

        for m in messages:
            if isinstance(m, HumanMessage) and not user_query:
                user_query = str(m.content)
            elif getattr(m, "type", "") == "tool" or hasattr(m, "tool_call_id"):
                context_snippets.append(str(m.content))

        joined_context = (
            "\n\n".join(context_snippets) if context_snippets else "No external tools invoked."
        )
        prompt = ANSWER_SYNTHESIS_PROMPT.format(query=user_query, context=joined_context[:8000])

        synthesis_messages = [
            SystemMessage(
                content="You are a senior codebase analyst synthesizing the final answer."
            ),
            HumanMessage(content=prompt),
        ]

        logger.info("AnswerNode: Synthesizing final response.")
        response = await self.llm.ainvoke(synthesis_messages)
        final_text = str(response.content)

        return {
            "messages": [AIMessage(content=final_text)],
            "final_answer": final_text,
        }
