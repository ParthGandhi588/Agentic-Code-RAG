"""Unit tests for Reciprocal Rank Fusion (RRF) algorithm."""

from src.retrieval.hybrid_engine import HybridRetrievalEngine
from src.retrieval.models import SearchResult


def test_rrf_blending_logic() -> None:
    # Item 1: High rank in Dense (rank 1), low rank in Sparse (rank 5)
    # Item 2: High in both Dense (rank 2) AND Sparse (rank 1) -> Should WIN overall!
    # Item 3: Only in Dense (rank 3)
    dense_items = [
        SearchResult(
            chunk_id=1,
            file_path="a.py",
            start_line=1,
            end_line=10,
            content="code 1",
            language="python",
            dense_score=0.95,
        ),
        SearchResult(
            chunk_id=2,
            file_path="b.py",
            start_line=1,
            end_line=10,
            content="code 2",
            language="python",
            dense_score=0.90,
        ),
        SearchResult(
            chunk_id=3,
            file_path="c.py",
            start_line=1,
            end_line=10,
            content="code 3",
            language="python",
            dense_score=0.85,
        ),
    ]

    sparse_items = [
        SearchResult(
            chunk_id=2,
            file_path="b.py",
            start_line=1,
            end_line=10,
            content="code 2",
            language="python",
            sparse_score=5.0,
        ),
        SearchResult(
            chunk_id=4,
            file_path="d.py",
            start_line=1,
            end_line=10,
            content="code 4",
            language="python",
            sparse_score=3.0,
        ),
        SearchResult(
            chunk_id=5,
            file_path="e.py",
            start_line=1,
            end_line=10,
            content="code 5",
            language="python",
            sparse_score=2.0,
        ),
        SearchResult(
            chunk_id=6,
            file_path="f.py",
            start_line=1,
            end_line=10,
            content="code 6",
            language="python",
            sparse_score=1.5,
        ),
        SearchResult(
            chunk_id=1,
            file_path="a.py",
            start_line=1,
            end_line=10,
            content="code 1",
            language="python",
            sparse_score=1.2,
        ),
    ]

    blended = HybridRetrievalEngine.compute_rrf(dense_items, sparse_items, rrf_k=60)

    # Item 2 has rank 2 in dense + rank 1 in sparse -> Combined 1/(60+2) + 1/(60+1) = 0.0325
    # Item 1 has rank 1 in dense + rank 5 in sparse -> Combined 1/(60+1) + 1/(60+5) = 0.0317
    # Therefore, Item 2 wins unambiguously
    assert blended[0].chunk_id == 2
    assert blended[1].chunk_id == 1
    assert blended[0].rrf_score > blended[1].rrf_score
