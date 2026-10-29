"""Corrective RAG (CRAG) Evaluator for grading retrieved context relevance."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from src.agent.prompts import CRAG_EVALUATOR_PROMPT
from src.agent.state import CRAGStatus
from src.core.logger import setup_logger

logger = setup_logger("agentic-crag")


class CRAGEvaluation(BaseModel):
    """Structured evaluation output assessing retrieved code relevance."""

    status: CRAGStatus = Field(
        description="Grade of retrieved context: relevant, insufficient, or irrelevant."
    )
    reasoning: str = Field(description="Explanation of why this grade was assigned.")
    missing_elements: list[str] = Field(
        default_factory=list,
        description="Missing symbols, methods, or files if context is insufficient.",
    )


class CRAGEvaluator:
    """Evaluates retrieved code context against the user query to prevent hallucinations."""

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm

    def heuristic_evaluate(self, query: str, context: str) -> CRAGEvaluation:
        """Fast deterministic grading based on lexical overlap, symbol density, and error markers.

        Used as an immediate evaluator or fallback when LLM is offline.
        """
        if (
            not context
            or "No matching code chunks found" in context
            or "No definition found" in context
        ):
            return CRAGEvaluation(
                status="irrelevant",
                reasoning="The retrieval tool returned no matching chunks or definitions.",
                missing_elements=[query],
            )

        query_tokens = set(re.findall(r"\w+", query.lower()))
        context_tokens = set(re.findall(r"\w+", context.lower()))

        # Remove generic English stop words from consideration
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "in",
            "it",
            "of",
            "to",
            "and",
            "or",
            "for",
            "how",
            "what",
            "where",
            "does",
            "used",
        }
        meaningful_query_tokens = query_tokens - stop_words

        if not meaningful_query_tokens:
            return CRAGEvaluation(
                status="relevant",
                reasoning="Query contains only generic tokens; accepting retrieved context.",
            )

        # Code-aware token matching: exact match or shared stem/substring (min length 4)
        matched_tokens: set[str] = set()
        for q_tok in meaningful_query_tokens:
            if q_tok in context_tokens or any(
                q_tok in c_tok or (len(q_tok) >= 4 and c_tok.startswith(q_tok[:4]))
                for c_tok in context_tokens
            ):
                matched_tokens.add(q_tok)

        ratio = len(matched_tokens) / len(meaningful_query_tokens)

        if ratio >= 0.5:
            return CRAGEvaluation(
                status="relevant",
                reasoning=f"High token and symbol alignment ({ratio:.1%}) between query and retrieved code.",
            )
        elif ratio >= 0.2:
            missing = list(meaningful_query_tokens - matched_tokens)
            return CRAGEvaluation(
                status="insufficient",
                reasoning=f"Partial alignment ({ratio:.1%}). Core concepts found but missing specific symbols.",
                missing_elements=missing,
            )
        else:
            return CRAGEvaluation(
                status="irrelevant",
                reasoning=f"Low alignment ({ratio:.1%}). Retrieved code appears unrelated to the target inquiry.",
                missing_elements=list(meaningful_query_tokens),
            )

    async def aevaluate(self, query: str, context: str) -> CRAGEvaluation:
        """Asynchronously grades the retrieved context using an LLM if available, falling back to heuristics."""
        if self.llm is None or "Ollama" in self.llm.__class__.__name__:
            return self.heuristic_evaluate(query=query, context=context)

        prompt_str = CRAG_EVALUATOR_PROMPT.format(query=query, context=context[:4000])
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(
                    content="You are a strict code relevance judge. Output valid JSON only."
                ),
                HumanMessage(content=prompt_str),
            ]
            response = await self.llm.ainvoke(messages)
            if isinstance(response.content, list):
                content = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in response.content
                )
            else:
                content = str(response.content)

            # Extract JSON block if wrapped in markdown
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                status_val = data.get("status", "insufficient").lower()
                if status_val not in ("relevant", "insufficient", "irrelevant"):
                    status_val = "insufficient"
                return CRAGEvaluation(
                    status=status_val,
                    reasoning=data.get("reasoning", "LLM graded evaluation."),
                    missing_elements=data.get("missing_elements", []),
                )
        except Exception as e:
            logger.warning(f"LLM CRAG evaluation failed, falling back to heuristics: {e}")

        return self.heuristic_evaluate(query=query, context=context)
