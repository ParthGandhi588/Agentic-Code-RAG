"""IDE-like autonomous agent tools for codebase navigation, AST inspection, and retrieval."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool

from src.core.config import get_settings
from src.core.logger import setup_logger
from src.parser.graph_store import CodeGraphStore
from src.retrieval.hybrid_engine import HybridRetrievalEngine

logger = setup_logger("agentic-tools")
settings = get_settings()


def _resolve_repo_id(repo_id: str) -> str:
    """Normalizes and resolves repo_id, falling back to Agentic-Code-RAG if not indexed or placeholder."""
    if not repo_id or not isinstance(repo_id, str):
        return "Agentic-Code-RAG"
    clean = repo_id.strip().strip("\"'")
    if clean in ("", "...", "default", "repo", "my-repo", "<repo_id>", "your-repo-id", "target-repo"):
        return "Agentic-Code-RAG"
    if clean in CodeGraphStore._symbols_cache:
        return clean
    if (Path(".rag_cache") / f"{clean}_symbols.json").is_file():
        return clean
    return "Agentic-Code-RAG"


@tool
async def inspect_repo_map(repo_id: str) -> str:
    """Inspect the high-level structural overview and PageRank central symbols of a repository.

    Args:
        repo_id: The unique identifier of the target repository.

    Returns:
        A hierarchical ASCII outline of the repository modules and key symbols.
    """
    repo_id = _resolve_repo_id(repo_id)
    try:
        defs = await CodeGraphStore.find_symbol_definitions(symbol_name="%", repo_id=repo_id)
        if not defs:
            return f"Repo Map for '{repo_id}' is empty or not yet indexed."

        lines = [f"# High-Level Topology: {repo_id}", f"Total identified symbols: {len(defs)}", ""]
        by_file: dict[str, list[str]] = {}
        for s in defs[:60]:
            by_file.setdefault(s.file_path, []).append(
                f"  - {s.kind.value}: {s.name} ({s.signature})"
            )

        for f_path, sym_list in sorted(by_file.items()):
            lines.append(f"{f_path}:")
            lines.extend(sym_list)

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"inspect_repo_map failed: {e}")
        return f"Error retrieving repo map for '{repo_id}': {e}"


@tool
async def find_symbol_definitions(repo_id: str, symbol_name: str) -> str:
    """Find the exact source code definition, signature, docstring, and line range of an AST symbol.

    Args:
        repo_id: The target repository identifier.
        symbol_name: The function, method, class, or interface name to locate.

    Returns:
        Formatted details of all matching symbol definitions.
    """
    repo_id = _resolve_repo_id(repo_id)
    clean_sym = symbol_name.strip().strip("\"'").removesuffix("()")
    try:
        symbols = await CodeGraphStore.find_symbol_definitions(
            symbol_name=clean_sym, repo_id=repo_id
        )
        if not symbols:
            return f"No definition found for symbol '{clean_sym}' in repository '{repo_id}'."

        output = [f"Found {len(symbols)} definition(s) for '{clean_sym}':"]
        for idx, sym in enumerate(symbols, 1):
            doc = f"\n   Docstring: {sym.docstring}" if sym.docstring else ""
            output.append(
                f"{idx}. {sym.file_path}:{sym.start_line}-{sym.end_line}\n"
                f"   Kind: {sym.kind.value}\n"
                f"   Signature: {sym.signature}"
                f"{doc}"
            )
        return "\n\n".join(output)
    except Exception as e:
        logger.warning(f"find_symbol_definitions failed for {symbol_name}: {e}")
        return f"Error searching for symbol '{symbol_name}': {e}"


@tool
async def find_symbol_references(repo_id: str, symbol_name: str) -> str:
    """Find callers and dependency relationships targeting a specific code symbol.

    Args:
        repo_id: The target repository identifier.
        symbol_name: The symbol whose call sites or dependencies to inspect.

    Returns:
        List of caller symbols, files, and relationship types.
    """
    repo_id = _resolve_repo_id(repo_id)
    clean_sym = symbol_name.strip().strip("\"'").removesuffix("()")
    try:
        edges = await CodeGraphStore.find_callers(target_symbol=clean_sym, repo_id=repo_id)
        if not edges:
            return f"No incoming references or callers found for '{clean_sym}' in repository '{repo_id}'."

        output = [f"Found {len(edges)} reference(s) for '{clean_sym}':"]
        for idx, edge in enumerate(edges, 1):
            target_info = f" -> {edge.target_file}" if edge.target_file else ""
            output.append(
                f"{idx}. {edge.source_file} [{edge.source_symbol}] --({edge.edge_type.value})--> {edge.target_symbol}{target_info}"
            )
        return "\n".join(output)
    except Exception as e:
        logger.warning(f"find_symbol_references failed for {clean_sym}: {e}")
        return f"Error finding references for '{clean_sym}': {e}"


@tool
async def hybrid_code_search(repo_id: str, query: str, top_k: int = 3) -> str:
    """Perform hybrid dense vector + lexical full-text search with FlashRank cross-encoder reranking.

    Args:
        repo_id: The target repository identifier.
        query: Conceptual or technical search query describing code functionality or symbols.
        top_k: Number of highest-ranked code snippets to return (default 3).

    Returns:
        Formatted code chunks with file paths, line ranges, reranker relevance scores, and content.
    """
    repo_id = _resolve_repo_id(repo_id)
    try:
        engine = HybridRetrievalEngine()
        results = await engine.search(repo_id=repo_id, query=query, top_k=min(3, top_k))
        if not results:
            return f"No matching code chunks found for query '{query}' in repository '{repo_id}'."

        output = [f"Retrieved {len(results)} relevant code chunk(s) for query '{query}':"]
        for idx, res in enumerate(results, 1):
            score_info = f"Rerank: {res.rerank_score:.4f}, RRF: {res.rrf_score:.4f}"
            lines = res.content.strip().splitlines()
            if len(lines) > 35:
                chunk_body = "\n".join(lines[:35]) + f"\n... [{len(lines)-35} more lines omitted for conciseness]"
            else:
                chunk_body = res.content.strip()
            output.append(
                f"--- Result {idx} | {res.file_path}:{res.start_line}-{res.end_line} [{score_info}] ---\n"
                f"{chunk_body}"
            )
        return "\n\n".join(output)
    except Exception as e:
        logger.warning(f"hybrid_code_search failed for query '{query}': {e}")
        return f"Error executing hybrid search for '{query}': {e}"


@tool
def read_file_range(
    repo_id: str,
    file_path: str,
    start_line: int = 1,
    end_line: int = 100,
) -> str:
    """Read a specific line range from a source code file with 1-indexed line numbers.

    Args:
        repo_id: The target repository identifier.
        file_path: Relative path to the file within the repository.
        start_line: 1-indexed starting line number (inclusive).
        end_line: 1-indexed ending line number (inclusive).

    Returns:
        The exact file lines prefixed with line numbers, or an informative error message.
    """
    repo_id = _resolve_repo_id(repo_id)
    clean_path = os.path.normpath(file_path.strip().strip("\"'")).lstrip("/")
    if ".." in clean_path.split(os.sep):
        return f"Access Denied: Path traversal detected in '{file_path}'."

    candidates = [
        Path(clean_path),
        Path.cwd() / clean_path,
        Path(settings.temp_dir) / repo_id / clean_path,
        Path(f"/home/parth/Desktop/Parth_Gandhi/{repo_id}") / clean_path,
    ]

    target_file: Path | None = None
    for cand in candidates:
        if cand.is_file():
            target_file = cand
            break

    if target_file is None:
        return f"File '{file_path}' not found on disk for repository '{repo_id}'."

    try:
        with open(target_file, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        if total_lines == 0:
            return f"File '{file_path}' is empty."

        s_line = max(1, start_line)
        e_line = min(total_lines, max(s_line, end_line))

        # Cap range to 120 lines for token safety and fast CPU inference
        if e_line - s_line > 120:
            e_line = s_line + 120

        sliced = all_lines[s_line - 1 : e_line]
        numbered_lines = [f"{s_line + i:4d} | {line.rstrip()}" for i, line in enumerate(sliced)]

        header = f"--- {clean_path} (Lines {s_line}-{e_line} of {total_lines}) ---\n"
        return header + "\n".join(numbered_lines)
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return f"Failed to read file '{file_path}': {e}"


@tool
def git_diff_analyzer(repo_id: str, revision_or_range: str = "HEAD~1..HEAD") -> str:
    """Analyze recent git diffs or commit changes for an indexed repository.

    Args:
        repo_id: The target repository identifier.
        revision_or_range: Git revision or range expression (e.g. 'HEAD~1..HEAD', 'main..HEAD').

    Returns:
        Summary of modified files and diff hunks.
    """
    clean_repo = repo_id.strip().strip("\"'")
    candidates = [
        Path(settings.temp_dir) / clean_repo,
        Path(f"/home/parth/Desktop/Parth_Gandhi/{clean_repo}"),
    ]
    if clean_repo in (Path.cwd().name, ".", "Agentic-Code-RAG", "current", "default"):
        candidates.append(Path.cwd())

    target_dir: Path | None = None
    for cand in candidates:
        if (cand / ".git").is_dir():
            target_dir = cand
            break

    if target_dir is None:
        return f"No git repository found for '{repo_id}'."

    try:
        import subprocess

        cmd = ["git", "diff", "--stat", revision_or_range]
        result = subprocess.run(
            cmd, cwd=target_dir, capture_output=True, text=True, timeout=10, check=False
        )
        if result.returncode != 0:
            return f"Git diff command failed: {result.stderr.strip()}"

        stat_output = result.stdout.strip()
        if not stat_output:
            return f"No changes detected for range '{revision_or_range}' in '{repo_id}'."

        # Fetch detailed patch limited to 3000 characters
        patch_cmd = ["git", "diff", "-U2", revision_or_range]
        patch_res = subprocess.run(
            patch_cmd, cwd=target_dir, capture_output=True, text=True, timeout=10, check=False
        )
        patch_text = patch_res.stdout[:3000]
        if len(patch_res.stdout) > 3000:
            patch_text += "\n... [diff truncated for length]"

        return f"### Git Diff Stat ({revision_or_range}):\n{stat_output}\n\n### Diff Hunks:\n{patch_text}"
    except Exception as e:
        return f"Error analyzing git diff for '{repo_id}': {e}"


ALL_AGENT_TOOLS = [
    inspect_repo_map,
    find_symbol_definitions,
    find_symbol_references,
    hybrid_code_search,
    read_file_range,
    git_diff_analyzer,
]
