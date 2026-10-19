"""Local cross-encoder reranker using FlashRank."""

from __future__ import annotations

from flashrank import Ranker, RerankRequest

from src.core.logger import setup_logger
from src.retrieval.models import SearchResult

logger = setup_logger("agentic-reranker")

_ranker: Ranker | None = None


def get_ranker() -> Ranker:
    """Initializes or returns cached singleton FlashRank cross-encoder."""
    global _ranker
    if _ranker is None:
        logger.info("Initializing local FlashRank cross-encoder (ms-marco-TinyBERT-L-2-v2)...")
        # ms-marco-TinyBERT-L-2-v2 is ultra-lightweight (4MB) and executes in < 5ms
        _ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    return _ranker


class LocalReranker:
    """Reranks candidate code chunks against user query using cross-attention."""

    @staticmethod
    def rerank(query: str, candidates: list[SearchResult], top_k: int = 5) -> list[SearchResult]:
        """Reranks candidates and returns the top_k most relevant chunks."""
        if not candidates:
            return []

        ranker = get_ranker()
        passages = [{"id": idx, "text": c.content, "meta": c} for idx, c in enumerate(candidates)]

        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        reranked_results: list[SearchResult] = []
        for r in results[:top_k]:
            original_result: SearchResult = r["meta"]
            original_result.rerank_score = float(r["score"])
            reranked_results.append(original_result)

        return reranked_results
