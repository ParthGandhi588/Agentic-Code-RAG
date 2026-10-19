"""AST-aware and sliding-window code chunker."""

from __future__ import annotations

from src.parser.models import CodeSymbol, SymbolKind
from src.retrieval.models import ChunkRecord


class CodeChunker:
    """Splits source files into semantically coherent code chunks."""

    def __init__(self, target_chunk_lines: int = 60, overlap_lines: int = 10) -> None:
        self.target_chunk_lines = target_chunk_lines
        self.overlap_lines = overlap_lines

    def chunk_file(
        self,
        file_path: str,
        content: str,
        language: str,
        symbols: list[CodeSymbol] | None = None,
    ) -> list[ChunkRecord]:
        """Partitions a file into structured chunks, prioritizing AST symbol boundaries."""
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks: list[ChunkRecord] = []
        covered_lines: set[int] = set()

        # 1. AST Symbol Chunks: classes, standalone functions, and interfaces
        if symbols:
            for sym in symbols:
                # Chunk class bodies or large functions
                if sym.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.INTERFACE):
                    s_idx = max(0, sym.start_line - 1)
                    e_idx = min(len(lines), sym.end_line)
                    symbol_lines = lines[s_idx:e_idx]

                    if symbol_lines:
                        chunk_text = (
                            f"--- File: {file_path}:{sym.start_line}-{sym.end_line} ({sym.qualified_name}) ---\n"
                            + "\n".join(symbol_lines)
                        )
                        chunks.append(
                            ChunkRecord(
                                file_path=file_path,
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                                content=chunk_text,
                                language=language,
                            )
                        )
                        for ln in range(sym.start_line, sym.end_line + 1):
                            covered_lines.add(ln)

        # 2. Window Sliding for un-covered code or non-AST files (markdown, configs, etc.)
        total_lines = len(lines)
        if len(covered_lines) < total_lines * 0.7 or not symbols:
            step = max(1, self.target_chunk_lines - self.overlap_lines)
            for start in range(0, total_lines, step):
                end = min(total_lines, start + self.target_chunk_lines)
                window_lines = lines[start:end]
                start_l, end_l = start + 1, end

                # Only emit if not completely covered by an existing symbol
                is_mostly_covered = all(ln in covered_lines for ln in range(start_l, end_l + 1))
                if not is_mostly_covered and window_lines:
                    chunk_text = f"--- File: {file_path}:{start_l}-{end_l} ---\n" + "\n".join(
                        window_lines
                    )
                    chunks.append(
                        ChunkRecord(
                            file_path=file_path,
                            start_line=start_l,
                            end_line=end_l,
                            content=chunk_text,
                            language=language,
                        )
                    )

        return chunks
