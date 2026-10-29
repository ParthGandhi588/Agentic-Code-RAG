"""PostgreSQL relational storage for AST code symbols and dependency edges with in-memory fallback."""

from __future__ import annotations

from collections import defaultdict

from src.core.disk_cache import load_cache, save_cache
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

    # In-memory fallback caches ensuring resilience during DB reconnects and tests
    _symbols_cache: dict[str, list[CodeSymbol]] = defaultdict(list)
    _edges_cache: dict[str, list[CodeEdge]] = defaultdict(list)

    @classmethod
    async def init_schema(cls) -> None:
        """Initializes the symbols and edges tables in PostgreSQL."""
        try:
            async with db_connection() as conn:
                await conn.execute(SCHEMA_SQL)
            logger.info("CodeGraph database schema verified.")
        except Exception as e:
            logger.warning(f"Could not initialize graph schema: {e}")

    @classmethod
    async def upsert_symbols(cls, symbols: list[CodeSymbol], repo_id: str) -> None:
        """Inserts or replaces code symbols for a repository."""
        if not symbols:
            return

        cls._symbols_cache[repo_id] = list(symbols)
        save_cache(f"{repo_id}_symbols", [s.model_dump() for s in symbols])

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
            logger.debug(f"Failed to upsert code symbols in DB, cached in memory/disk: {e}")

    @classmethod
    async def upsert_edges(cls, edges: list[CodeEdge], repo_id: str) -> None:
        """Inserts dependency edges for a repository."""
        if not edges:
            return

        cls._edges_cache[repo_id] = list(edges)
        save_cache(f"{repo_id}_edges", [e.model_dump() for e in edges])

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
            logger.debug(f"Failed to upsert code edges in DB, cached in memory/disk: {e}")

    @classmethod
    async def update_centrality_scores(cls, scores: dict[str, float], repo_id: str) -> None:
        """Updates PageRank centrality scores for symbols in a repository."""
        for sym in cls._symbols_cache.get(repo_id, []):
            if sym.name in scores:
                sym.centrality_score = scores[sym.name]
            elif sym.qualified_name in scores:
                sym.centrality_score = scores[sym.qualified_name]

        if repo_id in cls._symbols_cache:
            save_cache(f"{repo_id}_symbols", [s.model_dump() for s in cls._symbols_cache[repo_id]])

        query = """
            UPDATE code_symbols
            SET centrality_score = $1
            WHERE repo_id = $2 AND (name = $3 OR qualified_name = $3);
        """
        data = [(score, repo_id, sym_name) for sym_name, score in scores.items()]
        try:
            async with db_connection() as conn:
                await conn.executemany(query, data)
        except Exception as e:
            logger.debug(f"Failed to update centrality scores in DB: {e}")

    @classmethod
    async def find_symbol_definitions(cls, symbol_name: str, repo_id: str) -> list[CodeSymbol]:
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
                if rows:
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

        # Fallback to in-memory/disk cache
        if repo_id not in cls._symbols_cache or not cls._symbols_cache[repo_id]:
            disk_data = load_cache(f"{repo_id}_symbols")
            if disk_data:
                cls._symbols_cache[repo_id] = [CodeSymbol(**item) for item in disk_data]

        cached = cls._symbols_cache.get(repo_id, [])
        if symbol_name == "%":
            return list(cached)

        # 1. Exact match
        exact = [s for s in cached if s.name == symbol_name or s.qualified_name == symbol_name]
        if exact:
            return exact

        # 2. Cleaned name match (strips quotes, parens, prefixes)
        clean_name = (
            symbol_name.strip()
            .strip("\"'")
            .removesuffix("()")
            .removeprefix("class ")
            .removeprefix("def ")
            .strip()
        )
        cleaned_matches = [
            s for s in cached if s.name == clean_name or s.qualified_name == clean_name
        ]
        if cleaned_matches:
            return cleaned_matches

        # 3. Case-insensitive and qualified suffix match
        lower_clean = clean_name.lower()
        return [
            s
            for s in cached
            if s.name.lower() == lower_clean
            or s.qualified_name.lower().endswith("." + lower_clean)
        ]

    @classmethod
    async def find_callers(cls, target_symbol: str, repo_id: str) -> list[CodeEdge]:
        """Finds all callers and modules that import or call the target symbol."""
        query = """
            SELECT source_symbol, target_symbol, edge_type, source_file, target_file
            FROM code_edges
            WHERE repo_id = $1 AND (target_symbol = $2 OR target_file LIKE '%' || $2 || '%');
        """
        try:
            async with db_connection() as conn:
                rows = await conn.fetch(query, repo_id, target_symbol)
                if rows:
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

        # Fallback to in-memory/disk cache
        if repo_id not in cls._edges_cache or not cls._edges_cache[repo_id]:
            disk_data = load_cache(f"{repo_id}_edges")
            if disk_data:
                cls._edges_cache[repo_id] = [CodeEdge(**item) for item in disk_data]

        cached_edges = cls._edges_cache.get(repo_id, [])
        return [
            e
            for e in cached_edges
            if e.target_symbol == target_symbol
            or (e.target_file and target_symbol in e.target_file)
        ]
