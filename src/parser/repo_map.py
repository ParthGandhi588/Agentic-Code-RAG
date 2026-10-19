"""Centrality-Ranked Repository Map Generator using PageRank over AST symbols."""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from src.core.logger import setup_logger
from src.parser.models import CodeEdge, CodeSymbol, RepoMapSummary, SymbolKind

logger = setup_logger("agentic-repo-map")


class CentralityRepoMapBuilder:
    """Constructs a directed code graph, computes PageRank, and renders a token-budgeted Repo Map."""

    def __init__(self, damping: float = 0.85, max_chars: int = 6000) -> None:
        self.damping = damping
        self.max_chars = max_chars

    def _compute_pagerank(
        self, graph: nx.DiGraph, max_iter: int = 100, tol: float = 1e-6
    ) -> dict[str, float]:
        """Computes PageRank centrality using deterministic power iteration."""
        nodes = list(graph.nodes())
        N = len(nodes)
        if N == 0:
            return {}

        ranks: dict[str, float] = {node: 1.0 / N for node in nodes}

        for _ in range(max_iter):
            new_ranks: dict[str, float] = {}
            dangling_sum = sum(ranks[n] for n in nodes if graph.out_degree(n) == 0)

            for node in nodes:
                rank_sum = sum(
                    ranks[pred] / graph.out_degree(pred) for pred in graph.predecessors(node)
                )
                new_ranks[node] = (1.0 - self.damping) / N + self.damping * (
                    rank_sum + dangling_sum / N
                )

            diff = sum(abs(new_ranks[n] - ranks[n]) for n in nodes)
            ranks = new_ranks
            if diff < tol:
                break

        return ranks

    def build_map(
        self,
        repo_id: str,
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> RepoMapSummary:
        """Computes PageRank centrality over symbols and generates the structural Repo Map."""
        if not symbols:
            return RepoMapSummary(
                repo_id=repo_id,
                rendered_map="Empty repository (no symbols detected).",
                total_symbols=0,
                approx_tokens=0,
            )

        graph: nx.DiGraph = nx.DiGraph()

        # 1. Add all symbol and file nodes
        for sym in symbols:
            graph.add_node(sym.qualified_name, type="symbol", file=sym.file_path, symbol=sym)
            graph.add_node(sym.file_path, type="file")
            # Connect file -> symbol definition
            graph.add_edge(sym.file_path, sym.qualified_name, weight=1.0)

        # 2. Add relational edges
        for edge in edges:
            graph.add_node(edge.source_symbol)
            graph.add_node(edge.target_symbol)
            graph.add_edge(edge.source_symbol, edge.target_symbol, weight=1.0)

        # 3. Compute PageRank via self-contained power iteration (zero external C-library dependency)
        pagerank_scores = self._compute_pagerank(graph)

        # 4. Assign centrality scores back to symbols
        for sym in symbols:
            sym.centrality_score = pagerank_scores.get(sym.qualified_name, 0.0)

        # 5. Group symbols by file and sort by centrality
        files_to_symbols: dict[str, list[CodeSymbol]] = defaultdict(list)
        for sym in symbols:
            files_to_symbols[sym.file_path].append(sym)

        # 6. Render hierarchical ASCII outline
        rendered_lines: list[str] = [f"# Repository Map: {repo_id}", ""]
        current_char_count = 0
        top_symbols: list[tuple[str, float]] = []

        # Sort files alphabetically
        for file_path in sorted(files_to_symbols.keys()):
            file_symbols = files_to_symbols[file_path]
            # Sort symbols within file: classes first, then highest centrality
            file_symbols.sort(key=lambda s: (s.kind != SymbolKind.CLASS, -s.centrality_score))

            file_header = f"{file_path}:"
            rendered_lines.append(file_header)
            current_char_count += len(file_header) + 1

            for s in file_symbols:
                top_symbols.append((s.qualified_name, s.centrality_score))
                indent = (
                    "  "
                    if s.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.INTERFACE)
                    else "    "
                )
                sig_line = f"{indent}│ {s.signature}"

                # Append docstring summary if available
                if s.docstring:
                    first_doc_line = s.docstring.splitlines()[0][:60]
                    sig_line += f"  # {first_doc_line}"

                if current_char_count + len(sig_line) > self.max_chars:
                    rendered_lines.append("  │ ... (truncated due to token budget)")
                    break

                rendered_lines.append(sig_line)
                current_char_count += len(sig_line) + 1

            rendered_lines.append("")
            if current_char_count > self.max_chars:
                break

        final_map = "\n".join(rendered_lines)
        top_sorted = [name for name, _ in sorted(top_symbols, key=lambda x: -x[1])[:10]]

        return RepoMapSummary(
            repo_id=repo_id,
            rendered_map=final_map,
            total_symbols=len(symbols),
            top_central_symbols=top_sorted,
            approx_tokens=len(final_map) // 4,
        )
