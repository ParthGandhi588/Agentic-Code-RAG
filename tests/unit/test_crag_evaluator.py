"""Unit tests for the Corrective RAG (CRAG) Evaluator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.evaluator import CRAGEvaluator


def test_crag_heuristic_relevant() -> None:
    """Verifies that high token overlap yields 'relevant' status."""
    evaluator = CRAGEvaluator()
    query = "How is FastEmbed used for generating vector embeddings?"
    context = (
        "class LocalFastEmbedder:\n"
        "    def generate_embeddings(self, texts: list[str]):\n"
        "        # FastEmbed ONNX vector generator\n"
        "        return self.model.embed(texts)"
    )
    res = evaluator.heuristic_evaluate(query=query, context=context)
    assert res.status == "relevant"
    assert "High token and symbol alignment" in res.reasoning


def test_crag_heuristic_insufficient() -> None:
    """Verifies that partial overlap yields 'insufficient' status."""
    evaluator = CRAGEvaluator()
    query = "How is database migration handled in Alembic?"
    context = "We connect to the PostgreSQL database using asyncpg connection pool."
    res = evaluator.heuristic_evaluate(query=query, context=context)
    assert res.status == "insufficient"
    assert "Partial alignment" in res.reasoning
    assert "alembic" in res.missing_elements or "migration" in res.missing_elements


def test_crag_heuristic_irrelevant() -> None:
    """Verifies that zero overlap yields 'irrelevant' status."""
    evaluator = CRAGEvaluator()
    query = "Where is the React frontend routing configured?"
    context = (
        "No matching code chunks found for query 'frontend routing' in repository 'test_repo'."
    )
    res = evaluator.heuristic_evaluate(query=query, context=context)
    assert res.status == "irrelevant"


@pytest.mark.asyncio
async def test_crag_llm_evaluation() -> None:
    """Verifies LLM-based grading with JSON response parsing."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = '```json\n{"status": "relevant", "reasoning": "Direct implementation match.", "missing_elements": []}\n```'
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    evaluator = CRAGEvaluator(llm=mock_llm)
    res = await evaluator.aevaluate(query="find auth method", context="def authenticate(): pass")
    assert res.status == "relevant"
    assert res.reasoning == "Direct implementation match."
