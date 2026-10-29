"""Factory for instantiating LLM providers, constructing graphs, and streaming execution."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

from src.agent.graph import build_code_rag_graph
from src.agent.state import AgentState
from src.core.config import get_settings
from src.core.logger import setup_logger

logger = setup_logger("agentic-factory")
settings = get_settings()


def get_chat_llm(
    provider: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Instantiates a chat model based on application settings or explicit overrides."""
    prov = (provider or settings.llm_provider).lower()

    if prov == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name or settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            num_ctx=4096,
            num_thread=8,
        )

    elif prov == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name or settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    elif prov == "groq":
        from langchain_groq import ChatGroq

        secret_key = SecretStr(settings.groq_api_key) if settings.groq_api_key else None
        primary_model = model_name or settings.groq_model
        primary = ChatGroq(
            model=primary_model,
            api_key=secret_key,
            temperature=temperature,
            max_retries=3,
        )

        fallbacks: list[BaseChatModel] = []
        if secret_key:
            # Fallback 1: Alternate Groq model with independent token bucket
            secondary_model = (
                "openai/gpt-oss-20b"
                if primary_model != "openai/gpt-oss-20b"
                else "qwen/qwen3.8-27b"
            )
            fallbacks.append(
                ChatGroq(
                    model=secondary_model,
                    api_key=secret_key,
                    temperature=temperature,
                    max_retries=2,
                )
            )

        # Fallback 2: Google Gemini (if API key available)
        if settings.google_api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI

                fallbacks.append(
                    ChatGoogleGenerativeAI(
                        model=settings.gemini_model,
                        google_api_key=settings.google_api_key,
                        temperature=temperature,
                    )
                )
            except Exception:
                pass

        # Fallback 3: Local Ollama (always available offline)
        try:
            from langchain_ollama import ChatOllama

            fallbacks.append(
                ChatOllama(
                    model=settings.ollama_model,
                    base_url=settings.ollama_base_url,
                    temperature=temperature,
                    num_ctx=4096,
                    num_thread=8,
                )
            )
        except Exception:
            pass

        if fallbacks:
            return primary.with_fallbacks(fallbacks)
        return primary

    elif prov == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name or "gpt-4o",
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM provider '{prov}'. Expected one of: ollama, gemini, groq, openai."
    )


def create_agent(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph:
    """Constructs and compiles the Codebase RAG agent state machine."""
    chat_model = llm or get_chat_llm()
    return build_code_rag_graph(llm=chat_model, checkpointer=checkpointer)


async def stream_agent_events(
    agent: CompiledStateGraph,
    repo_id: str,
    query: str,
    thread_id: str = "default_thread",
    repo_map_summary: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    """Streams token events, tool calls, and CRAG evaluations in real time."""
    initial_state: AgentState = {
        "messages": [HumanMessage(content=query)],
        "repo_id": repo_id,
        "repo_map_summary": repo_map_summary,
        "discovered_symbols": [],
        "retrieved_chunks": [],
        "inspected_snippets": {},
        "crag_status": "pending",
        "iteration": 0,
        "max_iterations": 8,
        "final_answer": None,
        "error": None,
    }

    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    answer_tokens_emitted = 0

    async for event in agent.astream_events(initial_state, config=config, version="v2"):
        event_kind = event.get("event")
        metadata = event.get("metadata", {})
        node_name = metadata.get("langgraph_node", "")

        # Stream LLM generation tokens
        if event_kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and getattr(chunk, "content", None):
                raw_c = chunk.content
                if isinstance(raw_c, list):
                    text_c = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c)
                else:
                    text_c = str(raw_c)
                if text_c:
                    if node_name == "answer_node":
                        answer_tokens_emitted += 1
                        yield {"event": "token", "content": text_c}
                    elif node_name == "agent":
                        yield {"event": "thought_token", "content": text_c}

        # Stream Tool start events
        elif event_kind == "on_tool_start":
            tool_name = str(event.get("name", "tool"))
            tool_input: dict[str, Any] = dict(event.get("data", {}).get("input", {}))
            yield {"event": "tool_start", "tool": tool_name, "input": tool_input}

        # Stream Tool completion events
        elif event_kind == "on_tool_end":
            tool_name = str(event.get("name", "tool"))
            tool_output = event.get("data", {}).get("output", "")
            preview = str(tool_output)[:500]
            yield {"event": "tool_end", "tool": tool_name, "output_preview": preview}

        # Handle answer_node completion fallback if streaming had 0 tokens
        elif event_kind == "on_chain_end" and event.get("name") == "answer_node":
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and output.get("final_answer"):
                final_text = str(output["final_answer"])
                if answer_tokens_emitted == 0:
                    yield {"event": "token", "content": final_text}
                yield {"event": "final_answer", "answer": final_text}
