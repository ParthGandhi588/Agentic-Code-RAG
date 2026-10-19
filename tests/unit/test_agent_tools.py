"""Unit tests for the IDE agent toolbelt."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.tools.tools import (
    find_symbol_definitions,
    find_symbol_references,
    git_diff_analyzer,
    hybrid_code_search,
    read_file_range,
)
from src.parser.models import CodeEdge, CodeSymbol, EdgeType, SymbolKind
from src.retrieval.models import SearchResult


def test_read_file_range_valid(tmp_path: Path) -> None:
    """Verifies reading specific lines from a file with line numbers."""
    test_file = tmp_path / "sample.py"
    test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

    result = read_file_range.invoke(
        {"repo_id": "test_repo", "file_path": str(test_file), "start_line": 2, "end_line": 4}
    )
    assert "Lines 2-4 of 5" in result
    assert "2 | line2" in result
    assert "3 | line3" in result
    assert "4 | line4" in result
    assert "line1" not in result


def test_read_file_range_security_traversal() -> None:
    """Verifies that path traversal attacks (..) are blocked."""
    result = read_file_range.invoke(
        {"repo_id": "test_repo", "file_path": "../../etc/passwd", "start_line": 1, "end_line": 10}
    )
    assert "Access Denied: Path traversal detected" in result


def test_read_file_range_not_found() -> None:
    """Verifies handling when the requested file does not exist."""
    result = read_file_range.invoke(
        {
            "repo_id": "test_repo",
            "file_path": "non_existent_file.py",
            "start_line": 1,
            "end_line": 10,
        }
    )
    assert "not found on disk" in result


def test_git_diff_analyzer_no_git() -> None:
    """Verifies graceful reporting when target directory is not a git repo."""
    result = git_diff_analyzer.invoke(
        {"repo_id": "unknown_dummy_repo", "revision_or_range": "HEAD~1"}
    )
    assert "No git repository found" in result


@pytest.mark.asyncio
async def test_find_symbol_definitions_mocked() -> None:
    """Verifies formatted output when symbols are located."""
    mock_sym = CodeSymbol(
        file_path="src/auth.py",
        name="authenticate_user",
        qualified_name="auth.authenticate_user",
        kind=SymbolKind.FUNCTION,
        signature="def authenticate_user(token: str) -> bool",
        docstring="Validates JWT token signature.",
        start_line=10,
        end_line=25,
        language="python",
        centrality_score=0.95,
    )
    with patch(
        "src.agent.tools.tools.CodeGraphStore.find_symbol_definitions", new_callable=AsyncMock
    ) as mock_store:
        mock_store.return_value = [mock_sym]
        res = await find_symbol_definitions.ainvoke(
            {"repo_id": "test_repo", "symbol_name": "authenticate_user"}
        )
        assert "Found 1 definition(s)" in res
        assert "src/auth.py:10-25" in res
        assert "Validates JWT token signature" in res


@pytest.mark.asyncio
async def test_find_symbol_references_mocked() -> None:
    """Verifies formatted output for symbol call edges."""
    mock_edge = CodeEdge(
        source_symbol="login_handler",
        target_symbol="authenticate_user",
        edge_type=EdgeType.CALLS,
        source_file="src/routes.py",
        target_file="src/auth.py",
    )
    with patch(
        "src.agent.tools.tools.CodeGraphStore.find_callers", new_callable=AsyncMock
    ) as mock_store:
        mock_store.return_value = [mock_edge]
        res = await find_symbol_references.ainvoke(
            {"repo_id": "test_repo", "symbol_name": "authenticate_user"}
        )
        assert "Found 1 reference(s)" in res
        assert "src/routes.py [login_handler] --(CALLS)--> authenticate_user" in res


@pytest.mark.asyncio
async def test_hybrid_code_search_mocked() -> None:
    """Verifies formatted output for hybrid search results."""
    mock_result = SearchResult(
        chunk_id=1,
        file_path="src/parser/ast.py",
        start_line=15,
        end_line=30,
        content="class ASTParser:\n    def parse(self): pass",
        language="python",
        dense_score=0.88,
        sparse_score=12.5,
        rrf_score=0.032,
        rerank_score=0.945,
    )
    with patch(
        "src.agent.tools.tools.HybridRetrievalEngine.search", new_callable=AsyncMock
    ) as mock_search:
        mock_search.return_value = [mock_result]
        res = await hybrid_code_search.ainvoke(
            {"repo_id": "test_repo", "query": "ast parsing", "top_k": 3}
        )
        assert "Retrieved 1 relevant code chunk(s)" in res
        assert "src/parser/ast.py:15-30" in res
        assert "Rerank: 0.9450" in res
