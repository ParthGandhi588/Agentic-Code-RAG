"""Hybrid retrieval engine combining pgvector, tsvector, RRF, and FlashRank."""

from __future__ import annotations

import asyncio

from src.core.logger import setup_logger
from src.retrieval.embedder import FastEmbedder
from src.retrieval.models import SearchResult
from src.retrieval.reranker import LocalReranker
from src.retrieval.store import VectorStore

logger = setup_logger("agentic-hybrid-engine")


class HybridRetrievalEngine:
    """Orchestrates dense semantic search, sparse lexical BM25, Reciprocal Rank Fusion, and reranking."""

    def __init__(self, rrf_k: int = 60) -> None:
        self.rrf_k = rrf_k

    @staticmethod
    def compute_rrf(
        dense_results: list[SearchResult],
        sparse_results: list[SearchResult],
        rrf_k: int = 60,
    ) -> list[SearchResult]:
        """Merges dense and sparse ranked lists using Reciprocal Rank Fusion (RRF)."""
        rrf_scores: dict[int, float] = {}
        merged_map: dict[int, SearchResult] = {}

        # 1. Score dense candidates
        for rank, item in enumerate(dense_results, start=1):
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (rrf_k + rank))
            merged_map[item.chunk_id] = item

        # 2. Score sparse candidates
        for rank, item in enumerate(sparse_results, start=1):
            rrf_scores[item.chunk_id] = rrf_scores.get(item.chunk_id, 0.0) + (1.0 / (rrf_k + rank))
            if item.chunk_id not in merged_map:
                merged_map[item.chunk_id] = item
            else:
                merged_map[item.chunk_id].sparse_score = item.sparse_score

        # 3. Assign RRF score and sort descending
        results: list[SearchResult] = []
        for chunk_id, score in rrf_scores.items():
            record = merged_map[chunk_id]
            record.rrf_score = score
            results.append(record)

        results.sort(key=lambda x: x.rrf_score, reverse=True)
        return results

    async def search(
        self,
        query: str,
        repo_id: str,
        top_k: int = 5,
        dense_limit: int = 25,
        sparse_limit: int = 25,
    ) -> list[SearchResult]:
        """Executes full two-stage hybrid retrieval: dense+sparse RRF followed by cross-encoder reranking."""
        query_text = query.strip()
        if not query_text:
            return []

        # 1. Generate query embedding
        query_vec = await asyncio.to_thread(FastEmbedder.embed_query, query_text)

        # 2. Run dense and sparse searches concurrently
        dense_task = VectorStore.dense_search(query_vec, repo_id, limit=dense_limit)
        sparse_task = VectorStore.sparse_search(query_text, repo_id, limit=sparse_limit)

        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

        # 3. Reciprocal Rank Fusion
        blended_candidates = self.compute_rrf(dense_results, sparse_results, rrf_k=self.rrf_k)

        # 4. Local Cross-Encoder Reranking
        top_candidates = blended_candidates[:25]
        reranked = await asyncio.to_thread(LocalReranker.rerank, query_text, top_candidates, top_k)

        logger.info(
            f"Hybrid search '{query_text[:30]}...': Dense({len(dense_results)}) + Sparse({len(sparse_results)}) -> Reranked Top {len(reranked)}"
        )
        return reranked
