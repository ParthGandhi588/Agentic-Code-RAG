"""Unit tests for PageRank centrality and Repo Map generation."""

from src.parser.models import CodeEdge, CodeSymbol, EdgeType, SymbolKind
from src.parser.repo_map import CentralityRepoMapBuilder


def test_repo_map_pagerank_and_rendering() -> None:
    # Construct a mini repository structure
    # CoreModel is imported and referenced by both ServiceA and ServiceB
    symbols = [
        CodeSymbol(
            name="CoreModel",
            qualified_name="CoreModel",
            kind=SymbolKind.CLASS,
            file_path="src/models/core.py",
            start_line=1,
            end_line=10,
            signature="class CoreModel:",
            docstring="Core domain data model.",
            language="python",
        ),
        CodeSymbol(
            name="ServiceA",
            qualified_name="ServiceA",
            kind=SymbolKind.CLASS,
            file_path="src/services/service_a.py",
            start_line=1,
            end_line=20,
            signature="class ServiceA:",
            docstring="Processes user requests.",
            language="python",
        ),
        CodeSymbol(
            name="ServiceB",
            qualified_name="ServiceB",
            kind=SymbolKind.CLASS,
            file_path="src/services/service_b.py",
            start_line=1,
            end_line=25,
            signature="class ServiceB:",
            docstring="Background sync worker.",
            language="python",
        ),
    ]

    edges = [
        CodeEdge(
            source_symbol="src/services/service_a.py",
            target_symbol="CoreModel",
            edge_type=EdgeType.IMPORTS,
            source_file="src/services/service_a.py",
            target_file="src/models/core.py",
        ),
        CodeEdge(
            source_symbol="src/services/service_b.py",
            target_symbol="CoreModel",
            edge_type=EdgeType.IMPORTS,
            source_file="src/services/service_b.py",
            target_file="src/models/core.py",
        ),
    ]

    builder = CentralityRepoMapBuilder()
    summary = builder.build_map("my-app", symbols, edges)

    assert summary.total_symbols == 3
    assert len(summary.top_central_symbols) > 0

    # CoreModel has 2 incoming edges, so it must have higher centrality than the leaf services
    core_sym = next(s for s in symbols if s.name == "CoreModel")
    service_a_sym = next(s for s in symbols if s.name == "ServiceA")
    assert core_sym.centrality_score > service_a_sym.centrality_score

    # Verify rendered output contains file names and signatures
    rendered = summary.rendered_map
    assert "src/models/core.py:" in rendered
    assert "class CoreModel:" in rendered
    assert "src/services/service_a.py:" in rendered
