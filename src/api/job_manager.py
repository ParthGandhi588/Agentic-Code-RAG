"""Durable Background Job Manager orchestrating repository ingestion, AST parsing, and indexing."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from pathlib import Path

from src.api.job_store import JobStore
from src.api.schemas import IndexingJobResponse, JobStatus
from src.core.config import get_settings
from src.core.logger import setup_logger
from src.ingest.engine import IngestionEngine
from src.parser.ast_extractor import ASTSymbolExtractor
from src.parser.graph_store import CodeGraphStore
from src.parser.models import CodeEdge, CodeSymbol
from src.parser.repo_map import CentralityRepoMapBuilder
from src.retrieval.chunker import CodeChunker
from src.retrieval.embedder import FastEmbedder
from src.retrieval.models import ChunkRecord
from src.retrieval.store import VectorStore

logger = setup_logger("agentic-job-manager")
settings = get_settings()


class JobManager:
    """Orchestrates asynchronous indexing jobs and real-time SSE telemetry subscriptions."""

    # Real-time event subscription queues keyed by job_id
    _subscribers: dict[str, set[asyncio.Queue[IndexingJobResponse]]] = defaultdict(set)
    _active_tasks: dict[str, asyncio.Task[None]] = {}

    @classmethod
    async def create_and_start_job(
        cls,
        repo_id: str,
        source_type: str,
        source_path: str,
        branch: str | None = None,
    ) -> IndexingJobResponse:
        """Initializes a new indexing job in PostgreSQL/memory and launches background task."""
        job_id = str(uuid.uuid4())
        job = await JobStore.create_job(job_id=job_id, repo_id=repo_id)

        # Launch background task
        task = asyncio.create_task(
            cls._run_indexing_pipeline(
                job_id=job_id,
                repo_id=repo_id,
                source_type=source_type,
                source_path=source_path,
                branch=branch,
            )
        )
        cls._active_tasks[job_id] = task
        logger.info(
            f"Launched indexing job {job_id} for repo '{repo_id}' from source '{source_path}'."
        )
        return job

    @classmethod
    async def cancel_all(cls) -> None:
        """Cancels all active background tasks."""
        tasks = list(cls._active_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        cls._active_tasks.clear()

    @classmethod
    async def subscribe(cls, job_id: str) -> AsyncGenerator[IndexingJobResponse, None]:
        """Subscribes an SSE connection to live progress updates for an indexing job."""
        queue: asyncio.Queue[IndexingJobResponse] = asyncio.Queue()
        cls._subscribers[job_id].add(queue)

        try:
            # Yield initial snapshot immediately
            current_job = await JobStore.get_job(job_id)
            if current_job:
                yield current_job
                if current_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    return

            while True:
                update = await queue.get()
                yield update
                if update.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    break
        finally:
            cls._subscribers[job_id].discard(queue)
            if not cls._subscribers[job_id]:
                del cls._subscribers[job_id]

    @classmethod
    async def _broadcast(cls, update: IndexingJobResponse) -> None:
        """Pushes an updated job state to all subscribed SSE queues."""
        queues = list(cls._subscribers.get(update.job_id, []))
        for q in queues:
            await q.put(update)

    @classmethod
    async def _emit_progress(
        cls,
        job_id: str,
        status: JobStatus,
        progress_pct: int,
        phase: str,
        log_message: str | None = None,
        error_msg: str | None = None,
    ) -> IndexingJobResponse | None:
        """Updates persistent storage and broadcasts to real-time subscribers."""
        updated = await JobStore.update_progress(
            job_id=job_id,
            status=status,
            progress_pct=progress_pct,
            phase=phase,
            log_message=log_message,
            error_msg=error_msg,
        )
        if updated:
            await cls._broadcast(updated)
        return updated

    @classmethod
    async def _run_indexing_pipeline(
        cls,
        job_id: str,
        repo_id: str,
        source_type: str,
        source_path: str,
        branch: str | None = None,
    ) -> None:
        """Complete 4-phase indexing pipeline: Source Prep -> Scanning -> AST Parsing -> Embeddings."""
        temp_clone_dir: str | None = None
        working_path = source_path

        try:
            # -------------------------------------------------------------
            # Phase 1: Source Preparation / Cloning
            # -------------------------------------------------------------
            if source_type.lower() == "git" or source_path.startswith(
                ("http://", "https://", "git@")
            ):
                await cls._emit_progress(
                    job_id=job_id,
                    status=JobStatus.CLONING,
                    progress_pct=10,
                    phase="cloning",
                    log_message=f"Cloning remote repository '{source_path}'...",
                )
                temp_clone_dir = tempfile.mkdtemp(prefix=f"rag_clone_{repo_id}_")
                working_path = temp_clone_dir

                cmd = ["git", "clone", "--depth", "1"]
                if branch:
                    cmd.extend(["--branch", branch])
                cmd.extend([source_path, temp_clone_dir])

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Git clone failed: {stderr.decode(errors='replace').strip()}"
                    )

                await cls._emit_progress(
                    job_id=job_id,
                    status=JobStatus.CLONING,
                    progress_pct=20,
                    phase="cloning",
                    log_message="Git clone completed successfully.",
                )
            else:
                if not Path(working_path).exists():
                    raise FileNotFoundError(
                        f"Local source directory does not exist: {working_path}"
                    )
                await cls._emit_progress(
                    job_id=job_id,
                    status=JobStatus.CLONING,
                    progress_pct=15,
                    phase="source_verified",
                    log_message=f"Verified local source directory at '{working_path}'.",
                )

            # -------------------------------------------------------------
            # Phase 2: File Scanning & Git Deltas
            # -------------------------------------------------------------
            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.SCANNING,
                progress_pct=25,
                phase="scanning",
                log_message="Scanning files and computing SHA-256 / git delta hashes...",
            )

            engine = IngestionEngine()
            scan_result = await engine.ingest(source=working_path, repo_id=repo_id)

            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.SCANNING,
                progress_pct=40,
                phase="scanning",
                log_message=(
                    f"Scanned {scan_result.files_scanned} files "
                    f"(+{scan_result.files_added} ~{scan_result.files_modified} -{scan_result.files_deleted}) "
                    f"in {scan_result.elapsed_seconds}s."
                ),
            )

            # Read content for files that need indexing
            files_to_index = scan_result.indexed_files
            for f in files_to_index:
                if f.content is None:
                    try:
                        full_fpath = os.path.join(working_path, f.file_path)
                        with open(full_fpath, encoding="utf-8", errors="replace") as fh:
                            f.content = fh.read()
                    except Exception as e:
                        logger.debug(f"Could not read content for {f.file_path}: {e}")

            # -------------------------------------------------------------
            # Phase 3: AST Parsing & Centrality Repo Map
            # -------------------------------------------------------------
            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.AST_PARSING,
                progress_pct=50,
                phase="ast_parsing",
                log_message="Extracting Tree-sitter symbols and dependency call graphs...",
            )

            extractor = ASTSymbolExtractor()
            all_symbols: list[CodeSymbol] = []
            all_edges: list[CodeEdge] = []

            for f in files_to_index:
                if f.content and f.language:
                    syms, edges = extractor.extract(
                        file_path=f.file_path,
                        content=f.content,
                        language=f.language,
                    )
                    all_symbols.extend(syms)
                    all_edges.extend(edges)

            # Build PageRank Centrality Map (populates centrality_score on symbols)
            map_builder = CentralityRepoMapBuilder()
            map_builder.build_map(repo_id=repo_id, symbols=all_symbols, edges=all_edges)

            # Persist symbols and dependency edges with centrality scores
            await CodeGraphStore.upsert_symbols(all_symbols, repo_id=repo_id)
            await CodeGraphStore.upsert_edges(all_edges, repo_id=repo_id)

            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.AST_PARSING,
                progress_pct=70,
                phase="ast_parsing",
                log_message=f"Parsed {len(all_symbols)} AST symbols and {len(all_edges)} dependency edges.",
            )

            # -------------------------------------------------------------
            # Phase 4: Chunking & Hybrid Vector Embeddings
            # -------------------------------------------------------------
            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.INDEXING,
                progress_pct=75,
                phase="indexing",
                log_message="Chunking source code and computing dense vector embeddings...",
            )

            chunker = CodeChunker()
            all_chunks: list[ChunkRecord] = []
            # Index symbols by file for AST-aware chunking
            symbols_by_file: dict[str, list[CodeSymbol]] = defaultdict(list)
            for s in all_symbols:
                symbols_by_file[s.file_path].append(s)

            for f in files_to_index:
                if f.content:
                    file_chunks = chunker.chunk_file(
                        file_path=f.file_path,
                        content=f.content,
                        language=f.language or "unknown",
                        symbols=symbols_by_file.get(f.file_path),
                    )
                    all_chunks.extend(file_chunks)

            if all_chunks:
                chunk_texts = [c.content for c in all_chunks]
                embeddings = FastEmbedder.embed_documents(chunk_texts)
                for c, emb in zip(all_chunks, embeddings, strict=True):
                    c.embedding = emb

                await VectorStore.upsert_chunks(all_chunks, repo_id=repo_id)

            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.INDEXING,
                progress_pct=95,
                phase="indexing",
                log_message=f"Indexed {len(all_chunks)} code chunks into pgvector and tsvector.",
            )

            # -------------------------------------------------------------
            # Phase 5: Pipeline Completed
            # -------------------------------------------------------------
            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                progress_pct=100,
                phase="completed",
                log_message=f"Indexing successfully completed for repository '{repo_id}'.",
            )
            logger.info(f"Indexing job {job_id} for '{repo_id}' completed successfully.")

        except Exception as e:
            logger.error(f"Indexing pipeline failed for job {job_id}: {e}", exc_info=True)
            await cls._emit_progress(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress_pct=0,
                phase="failed",
                log_message=f"Job failed with error: {e}",
                error_msg=str(e),
            )
        finally:
            if temp_clone_dir and os.path.exists(temp_clone_dir):
                try:
                    shutil.rmtree(temp_clone_dir, ignore_errors=True)
                except Exception as e:
                    logger.debug(f"Failed to cleanup temp clone directory {temp_clone_dir}: {e}")
            cls._active_tasks.pop(job_id, None)
