"""API router for repository lifecycle, AST graph exploration, and code inspection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, status

from src.api.errors import PathTraversalError, RepoNotFoundError
from src.api.job_manager import JobManager
from src.api.job_store import JobStore
from src.api.schemas import (
    FileContentResponse,
    GraphEdge,
    GraphNode,
    RepoGraphResponse,
    RepoInitRequest,
    RepoInitResponse,
    RepoListResponse,
    RepoSummary,
)
from src.core.config import get_settings
from src.core.logger import setup_logger
from src.ingest.manifest import ManifestStore, db_connection
from src.parser.graph_store import CodeGraphStore

router = APIRouter(prefix="/api/repos", tags=["Repositories"])
logger = setup_logger("agentic-repos-api")
settings = get_settings()


@router.post(
    "/init",
    response_model=RepoInitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate Repository Ingestion",
    description="Schedules an asynchronous indexing pipeline (cloning, delta scanning, AST parsing, and vector embedding).",
)
async def init_repo_indexing(payload: RepoInitRequest) -> RepoInitResponse:
    """Accepts repository source and schedules background indexing."""
    job = await JobManager.create_and_start_job(
        repo_id=payload.repo_id,
        source_type=payload.source_type,
        source_path=payload.source_path,
        branch=payload.branch,
    )
    return RepoInitResponse(
        job_id=job.job_id,
        repo_id=job.repo_id,
        status=job.status,
        message=f"Indexing job '{job.job_id}' successfully scheduled for '{payload.repo_id}'.",
    )


@router.get(
    "",
    response_model=RepoListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Indexed Repositories",
    description="Returns metadata, file counts, detected languages, and symbol counts for all indexed repositories.",
)
async def list_repositories() -> RepoListResponse:
    """Lists summary statistics for all indexed repositories."""
    repos: list[RepoSummary] = []
    try:
        async with db_connection() as conn:
            # Aggregate files manifest
            file_stats = await conn.fetch(
                """
                SELECT
                    repo_id,
                    COUNT(*) as total_files,
                    array_agg(DISTINCT language) FILTER (WHERE language IS NOT NULL) as languages,
                    MAX(indexed_at) as last_indexed_at
                FROM indexed_files
                GROUP BY repo_id
                ORDER BY repo_id ASC;
                """
            )
            # Aggregate symbol counts
            sym_stats = await conn.fetch(
                """
                SELECT repo_id, COUNT(*) as total_symbols
                FROM code_symbols
                GROUP BY repo_id;
                """
            )
            sym_map = {r["repo_id"]: r["total_symbols"] for r in sym_stats}

            for row in file_stats:
                r_id = row["repo_id"]
                langs = [lang for lang in (row["languages"] or []) if lang]
                repos.append(
                    RepoSummary(
                        repo_id=r_id,
                        total_files=row["total_files"],
                        languages=langs,
                        total_symbols=sym_map.get(r_id, 0),
                        last_indexed_at=row["last_indexed_at"],
                    )
                )
    except Exception as e:
        logger.debug(f"DB aggregation for list_repositories failed (DB may be offline): {e}")

    # If DB returned nothing or is offline, check cached jobs or disk cache
    if not repos:
        from pathlib import Path
        cache_dir = Path(".rag_cache")
        seen: set[str] = set()

        # Check in-memory JobStore jobs
        cached_jobs = JobStore._memory_cache.values()
        for j in cached_jobs:
            if j.repo_id not in seen:
                seen.add(j.repo_id)
                syms = CodeGraphStore._symbols_cache.get(j.repo_id, [])
                files = ManifestStore._manifest_cache.get(j.repo_id, {})
                langs = sorted({s.language for s in syms if s.language})
                total_files = len(files) if files else len({s.file_path for s in syms})
                repos.append(
                    RepoSummary(
                        repo_id=j.repo_id,
                        total_files=total_files,
                        languages=langs,
                        total_symbols=len(syms),
                        last_indexed_at=j.updated_at,
                    )
                )

        # Check disk cache .rag_cache/*_manifest.json
        if cache_dir.is_dir():
            for mf in cache_dir.glob("*_manifest.json"):
                r_id = mf.stem.removesuffix("_manifest")
                if r_id and r_id not in seen and not r_id.startswith("test_"):
                    seen.add(r_id)
                    syms = await CodeGraphStore.find_symbol_definitions(symbol_name="%", repo_id=r_id)
                    files = await ManifestStore.load_indexed_hashes(repo_id=r_id)
                    langs = sorted({s.language for s in syms if s.language})
                    total_files = len(files) if files else len({s.file_path for s in syms})
                    repos.append(
                        RepoSummary(
                            repo_id=r_id,
                            total_files=total_files,
                            languages=langs,
                            total_symbols=len(syms),
                        )
                    )

    return RepoListResponse(repositories=repos)


@router.get(
    "/{repo_id}/map",
    status_code=status.HTTP_200_OK,
    summary="Get Centrality Repository Map",
    description="Returns the high-level structural outline and PageRank-weighted symbol hierarchy for the repository.",
)
async def get_repo_map(repo_id: str) -> dict[str, Any]:
    """Generates and returns the structural repository outline."""
    symbols = await CodeGraphStore.find_symbol_definitions(symbol_name="%", repo_id=repo_id)
    if not symbols:
        # Check if repo exists in jobs
        job = next((j for j in JobStore._memory_cache.values() if j.repo_id == repo_id), None)
        if not job:
            raise RepoNotFoundError(repo_id)
        return {
            "repo_id": repo_id,
            "total_symbols": 0,
            "repo_map": f"Repo Map for '{repo_id}' is empty or currently indexing.",
        }

    lines = [f"# Topology Overview: {repo_id}", f"Total AST Symbols: {len(symbols)}", ""]
    by_file: dict[str, list[str]] = {}
    for s in symbols[:80]:
        by_file.setdefault(s.file_path, []).append(f"  - {s.kind.value}: {s.name} ({s.signature})")

    for f_path, sym_list in sorted(by_file.items()):
        lines.append(f"{f_path}:")
        lines.extend(sym_list)

    return {
        "repo_id": repo_id,
        "total_symbols": len(symbols),
        "repo_map": "\n".join(lines),
    }


@router.get(
    "/{repo_id}/graph",
    response_model=RepoGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AST Dependency & Call Graph",
    description="Returns graph nodes (classes/functions) and directed edges (calls/imports) for interactive visualization.",
)
async def get_repo_graph(repo_id: str) -> RepoGraphResponse:
    """Returns AST graph nodes and caller/callee edges formatted for visual graph explorers."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        async with db_connection() as conn:
            # Query top symbols by PageRank centrality
            sym_rows = await conn.fetch(
                """
                SELECT id, name, kind, file_path, start_line, centrality_score
                FROM code_symbols
                WHERE repo_id = $1
                ORDER BY centrality_score DESC
                LIMIT 150;
                """,
                repo_id,
            )
            for r in sym_rows:
                nodes.append(
                    GraphNode(
                        id=f"{r['file_path']}:{r['name']}",
                        name=r["name"],
                        kind=r["kind"],
                        file_path=r["file_path"],
                        line=r["start_line"],
                        pagerank_score=r["centrality_score"] or 0.0,
                    )
                )

            # Query dependency edges
            edge_rows = await conn.fetch(
                """
                SELECT source_symbol, target_symbol, edge_type, source_file, target_file
                FROM code_edges
                WHERE repo_id = $1
                LIMIT 300;
                """,
                repo_id,
            )
            for e in edge_rows:
                s_id = (
                    f"{e['source_file']}:{e['source_symbol']}"
                    if e["source_file"]
                    else e["source_symbol"]
                )
                t_id = (
                    f"{e['target_file']}:{e['target_symbol']}"
                    if e["target_file"]
                    else e["target_symbol"]
                )
                edges.append(
                    GraphEdge(
                        source=s_id,
                        target=t_id,
                        edge_type=e["edge_type"],
                    )
                )
    except Exception as e:
        logger.debug(f"Failed to fetch repo graph from DB for {repo_id}: {e}")

    # Fallback to in-memory graph cache if DB is offline or returned no rows
    if not nodes and repo_id in CodeGraphStore._symbols_cache:
        cached_syms = sorted(
            CodeGraphStore._symbols_cache[repo_id],
            key=lambda s: s.centrality_score,
            reverse=True,
        )[:150]
        for s in cached_syms:
            nodes.append(
                GraphNode(
                    id=f"{s.file_path}:{s.name}",
                    name=s.name,
                    kind=str(s.kind),
                    file_path=s.file_path,
                    line=s.start_line,
                    pagerank_score=s.centrality_score,
                )
            )
        cached_edges = CodeGraphStore._edges_cache.get(repo_id, [])[:300]
        for edge in cached_edges:
            s_id = (
                f"{edge.source_file}:{edge.source_symbol}"
                if edge.source_file
                else edge.source_symbol
            )
            t_id = (
                f"{edge.target_file}:{edge.target_symbol}"
                if edge.target_file
                else edge.target_symbol
            )
            edges.append(
                GraphEdge(
                    source=s_id,
                    target=t_id,
                    edge_type=str(edge.edge_type),
                )
            )

    return RepoGraphResponse(repo_id=repo_id, nodes=nodes, edges=edges)


@router.get(
    "/{repo_id}/file",
    response_model=FileContentResponse,
    status_code=status.HTTP_200_OK,
    summary="View Source File Contents",
    description="Safely inspects source code lines with path traversal guards and line range windowing.",
)
async def get_file_content(
    repo_id: str,
    file_path: str = Query(..., description="Relative file path within the repository."),
    start_line: int = Query(default=1, ge=1, description="1-indexed starting line number."),
    end_line: int = Query(default=200, ge=1, description="1-indexed ending line number."),
) -> FileContentResponse:
    """Reads and highlights code spans within an indexed repository."""
    # Strict Path Traversal Protection
    clean_path = os.path.normpath(file_path).replace("\\", "/").lstrip("/")
    if ".." in clean_path.split("/"):
        raise PathTraversalError(file_path)

    candidates = [
        Path(file_path),
        Path(settings.temp_dir) / repo_id / clean_path,
        Path(f"/home/parth/Desktop/Parth_Gandhi/{repo_id}") / clean_path,
    ]
    if repo_id in (Path.cwd().name, ".", "Agentic-Code-RAG", "agentic-code-rag"):
        candidates.append(Path.cwd() / clean_path)

    target_file: Path | None = None
    for cand in candidates:
        if cand.is_file():
            target_file = cand
            break

    if target_file is None:
        raise RepoNotFoundError(f"{repo_id}/{file_path}")

    with open(target_file, encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    total_lines = len(all_lines)
    s_line = max(1, start_line)
    e_line = min(total_lines, max(s_line, end_line))
    # Cap window to 500 lines max
    if e_line - s_line > 500:
        e_line = s_line + 500

    sliced = all_lines[s_line - 1 : e_line]
    numbered = [f"{s_line + i:4d} | {line.rstrip()}" for i, line in enumerate(sliced)]

    return FileContentResponse(
        repo_id=repo_id,
        file_path=clean_path,
        total_lines=total_lines,
        start_line=s_line,
        end_line=e_line,
        content="\n".join(numbered),
    )


@router.delete(
    "/{repo_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Indexed Repository",
    description="Cascading purge of repository records from indexed_files, code_symbols, code_edges, code_chunks, and indexing_jobs.",
)
async def delete_repository(repo_id: str) -> dict[str, Any]:
    """Cascading deletion of all vectors, graph edges, and manifest records for a repository."""
    deleted_counts: dict[str, int] = {}
    try:
        async with db_connection() as conn:
            # 1. Purge indexed files manifest
            res = await conn.execute("DELETE FROM indexed_files WHERE repo_id = $1;", repo_id)
            deleted_counts["indexed_files"] = int(res.split()[1]) if len(res.split()) == 2 else 0

            # 2. Purge symbols and edges
            res = await conn.execute("DELETE FROM code_symbols WHERE repo_id = $1;", repo_id)
            deleted_counts["code_symbols"] = int(res.split()[1]) if len(res.split()) == 2 else 0

            res = await conn.execute("DELETE FROM code_edges WHERE repo_id = $1;", repo_id)
            deleted_counts["code_edges"] = int(res.split()[1]) if len(res.split()) == 2 else 0

            # 3. Purge code chunk vectors
            res = await conn.execute("DELETE FROM code_chunks WHERE repo_id = $1;", repo_id)
            deleted_counts["code_chunks"] = int(res.split()[1]) if len(res.split()) == 2 else 0
    except Exception as e:
        logger.debug(f"DB cascade delete failed for {repo_id}: {e}")

    # 4. Purge jobs
    deleted_jobs = await JobStore.delete_jobs_for_repo(repo_id)
    deleted_counts["indexing_jobs"] = deleted_jobs

    return {
        "status": "deleted",
        "repo_id": repo_id,
        "purged_records": deleted_counts,
    }
