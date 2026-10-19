"""PostgreSQL relational storage for AST code symbols and dependency edges."""

from __future__ import annotations

from src.core.logger import setup_logger
from src.ingest.manifest import db_connection
from src.parser.models import CodeEdge, CodeSymbol, EdgeType, SymbolKind

logger = setup_logger("agentic-graph-store")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS code_symbols (
    id BIGSERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    name VARCHAR(255) NOT NULL,
    qualified_name TEXT NOT NULL,
    kind VARCHAR(50) NOT NULL,
    signature TEXT,
    docstring TEXT,
    start_line INT NOT NULL,
    end_line INT NOT NULL,
    language VARCHAR(50) NOT NULL,
    centrality_score DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_code_symbols_repo_name ON code_symbols(repo_id, name);
CREATE INDEX IF NOT EXISTS idx_code_symbols_repo_file ON code_symbols(repo_id, file_path);
CREATE INDEX IF NOT EXISTS idx_code_symbols_centrality ON code_symbols(repo_id, centrality_score DESC);

CREATE TABLE IF NOT EXISTS code_edges (
    id BIGSERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    source_symbol TEXT NOT NULL,
    target_symbol TEXT NOT NULL,
    edge_type VARCHAR(50) NOT NULL,
    source_file TEXT NOT NULL,
    target_file TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_code_edges_repo_source ON code_edges(repo_id, source_symbol);
CREATE INDEX IF NOT EXISTS idx_code_edges_repo_target ON code_edges(repo_id, target_symbol);
"""


class CodeGraphStore:
    """Manages persistence and relational queries for symbols and call graph edges."""

    @staticmethod
    async def init_schema() -> None:
        """Initializes the symbols and edges tables in PostgreSQL."""
        try:
            async with db_connection() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("CodeGraph database schema verified.")
        except Exception as e:
            logger.warning(f"Could not initialize graph schema: {e}")

    @staticmethod
    async def upsert_symbols(symbols: list[CodeSymbol], repo_id: str) -> None:
        """Inserts or replaces code symbols for a repository."""
        if not symbols:
            return

        query = """
            INSERT INTO code_symbols
                (repo_id, file_path, name, qualified_name, kind, signature, docstring, start_line, end_line, language, centrality_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
        """
        data = [
            (
                repo_id,
                s.file_path,
                s.name,
                s.qualified_name,
                str(s.kind),
                s.signature,
                s.docstring,
                s.start_line,
                s.end_line,
                s.language,
                s.centrality_score,
            )
            for s in symbols
        ]
        try:
            async with db_connection() as conn:
                await conn.executemany(query, data)
            logger.info(f"GraphStore: Saved {len(symbols)} symbols for repo {repo_id}")
        except Exception as e:
            logger.error(f"Failed to upsert code symbols: {e}")

    @staticmethod
    async def upsert_edges(edges: list[CodeEdge], repo_id: str) -> None:
        """Inserts dependency edges for a repository."""
        if not edges:
            return

        query = """
            INSERT INTO code_edges
                (repo_id, source_symbol, target_symbol, edge_type, source_file, target_file)
            VALUES ($1, $2, $3, $4, $5, $6);
        """
        data = [
            (
                repo_id,
                e.source_symbol,
                e.target_symbol,
                str(e.edge_type),
                e.source_file,
                e.target_file,
            )
            for e in edges
        ]
        try:
            async with db_connection() as conn:
                await conn.executemany(query, data)
            logger.info(f"GraphStore: Saved {len(edges)} edges for repo {repo_id}")
        except Exception as e:
            logger.error(f"Failed to upsert code edges: {e}")

    @staticmethod
    async def find_symbol_definitions(symbol_name: str, repo_id: str) -> list[CodeSymbol]:
        """Deterministic symbol lookup: finds exact definition locations of a function, class, or method."""
        query = """
            SELECT file_path, name, qualified_name, kind, signature, docstring, start_line, end_line, language, centrality_score
            FROM code_symbols
            WHERE repo_id = $1 AND (name = $2 OR qualified_name = $2)
            ORDER BY centrality_score DESC;
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, repo_id, symbol_name)
                return [
                    CodeSymbol(
                        file_path=r["file_path"],
                        name=r["name"],
                        qualified_name=r["qualified_name"],
                        kind=SymbolKind(r["kind"]),
                        signature=r["signature"] or "",
                        docstring=r["docstring"],
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        language=r["language"],
                        centrality_score=r["centrality_score"],
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"Failed to find symbol definition for {symbol_name}: {e}")
            return []

    @staticmethod
    async def find_callers(target_symbol: str, repo_id: str) -> list[CodeEdge]:
        """Finds all callers and modules that import or call the target symbol."""
        query = """
            SELECT source_symbol, target_symbol, edge_type, source_file, target_file
            FROM code_edges
            WHERE repo_id = $1 AND (target_symbol = $2 OR target_file LIKE '%' || $2 || '%');
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, repo_id, target_symbol)
                return [
                    CodeEdge(
                        source_symbol=r["source_symbol"],
                        target_symbol=r["target_symbol"],
                        edge_type=EdgeType(r["edge_type"]),
                        source_file=r["source_file"],
                        target_file=r["target_file"],
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"Failed to find callers for {target_symbol}: {e}")
            return []
