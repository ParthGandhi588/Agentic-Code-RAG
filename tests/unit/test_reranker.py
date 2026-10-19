"""Unit tests for local FlashRank cross-encoder reranking."""

from src.retrieval.models import SearchResult
from src.retrieval.reranker import LocalReranker


def test_local_cross_encoder_rerank() -> None:
    query = "validate jwt token bearer authentication"

    candidates = [
        SearchResult(
            chunk_id=1,
            file_path="src/ui/button.tsx",
            start_line=1,
            end_line=20,
            content="export const Button = ({ label }) => <button className='btn'>{label}</button>;",
            language="typescript",
        ),
        SearchResult(
            chunk_id=2,
            file_path="src/auth/jwt.py",
            start_line=1,
            end_line=25,
            content="def verify_jwt_token(token: str) -> dict:\n    '''Decodes and validates JWT bearer authorization headers.'''\n    return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])",
            language="python",
        ),
        SearchResult(
            chunk_id=3,
            file_path="src/db/connection.py",
            start_line=1,
            end_line=15,
            content="def get_db():\n    conn = psycopg2.connect(DATABASE_URL)\n    return conn",
            language="python",
        ),
    ]

    reranked = LocalReranker.rerank(query, candidates, top_k=2)

    assert len(reranked) == 2
    # The JWT verification chunk MUST be ranked #1
    assert reranked[0].chunk_id == 2
    assert reranked[0].rerank_score > reranked[1].rerank_score
