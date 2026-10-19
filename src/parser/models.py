"""Data models for AST symbols, edges, and repository maps."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SymbolKind(StrEnum):
    """Kind of syntactic code entity."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    VARIABLE = "variable"


class EdgeType(StrEnum):
    """Type of relational dependency between symbols or files."""

    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    DEFINES = "DEFINES"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"


class CodeSymbol(BaseModel):
    """An extracted code symbol (class, function, method, interface)."""

    name: str
    qualified_name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str | None = None
    language: str
    centrality_score: float = 0.0


class CodeEdge(BaseModel):
    """A directed dependency edge between two symbols or modules."""

    source_symbol: str
    target_symbol: str
    edge_type: EdgeType
    source_file: str
    target_file: str | None = None


class RepoMapSummary(BaseModel):
    """Rendered repository map with centrality metrics."""

    repo_id: str
    rendered_map: str
    total_symbols: int
    top_central_symbols: list[str] = Field(default_factory=list)
    approx_tokens: int = 0
