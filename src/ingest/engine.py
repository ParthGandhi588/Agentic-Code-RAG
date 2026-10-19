"""Master Ingestion Engine coordinating Git-native deltas and parallel scanning."""

import hashlib
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

from src.core.config import get_settings
from src.core.logger import setup_logger
from src.ingest.detector import detect_language
from src.ingest.filters import SecuritySanitizer, load_gitignore_spec
from src.ingest.git_scanner import GitScanner
from src.ingest.manifest import ManifestStore
from src.ingest.models import FileChangeType, IngestionResult, ScannedFile

logger = setup_logger("agentic-ingestion-engine")
settings = get_settings()


class IngestionEngine:
    """Orchestrates Git-native delta detection, parallel scanning, and manifest tracking."""

    def __init__(self, max_workers: int = 16) -> None:
        self.max_workers = max_workers
        self.sanitizer = SecuritySanitizer()

    def _compute_hash(self, data: bytes) -> str:
        """Computes SHA-256 hash of file content."""
        return hashlib.sha256(data).hexdigest()

    def _resolve_source_path(self, source: str) -> str:
        """Resolves local folders, clones git repositories, or unzips archives."""
        source_clean = source.strip()

        # Remote Git Repository URL
        if (
            source_clean.startswith("http://")
            or source_clean.startswith("https://")
            or source_clean.startswith("git@")
        ):
            repo_hash = hashlib.md5(source_clean.encode()).hexdigest()[:12]
            target_dir = os.path.join(settings.temp_dir, f"repo_{repo_hash}")
            return GitScanner.clone_repo(source_clean, target_dir)

        # ZIP Archive
        if source_clean.endswith(".zip") and os.path.isfile(source_clean):
            zip_hash = hashlib.md5(source_clean.encode()).hexdigest()[:12]
            target_dir = os.path.join(settings.temp_dir, f"zip_{zip_hash}")
            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(source_clean, "r") as z:
                z.extractall(target_dir)
            return target_dir

        # Local Directory
        if os.path.isdir(source_clean):
            return os.path.abspath(source_clean)

        raise ValueError(
            f"Invalid repository source: '{source}'. Must be a local folder, git URL, or .zip file."
        )

    async def ingest(self, source: str, repo_id: str | None = None) -> IngestionResult:
        """Runs the ingestion pipeline: detects changes, filters files, and updates manifest."""
        start_time = time.perf_counter()
        root_path = self._resolve_source_path(source)
        resolved_repo_id = repo_id or os.path.basename(root_path.rstrip("/\\"))

        logger.info(f"Starting ingestion for repo '{resolved_repo_id}' at {root_path}")

        is_git = GitScanner.is_git_repo(root_path)
        head_commit = GitScanner.get_head_commit(root_path) if is_git else None
        last_commit = (
            await ManifestStore.get_last_indexed_commit(resolved_repo_id) if is_git else None
        )

        result = IngestionResult(
            repo_id=resolved_repo_id,
            source_path=root_path,
            commit_sha=head_commit,
        )

        # ------------------------------------------------------------------
        # Fast-Path A: Unchanged Git Repository
        # ------------------------------------------------------------------
        if is_git and last_commit and head_commit and last_commit == head_commit:
            logger.info(f"Git commit {head_commit[:8]} already indexed. 0 changes detected.")
            hashes = await ManifestStore.load_indexed_hashes(resolved_repo_id)
            result.files_scanned = len(hashes)
            result.files_unchanged = len(hashes)
            result.elapsed_seconds = round(time.perf_counter() - start_time, 4)
            return result

        # ------------------------------------------------------------------
        # Fast-Path B: Incremental Git Delta via git diff-tree
        # ------------------------------------------------------------------
        if is_git and last_commit and head_commit:
            logger.info(
                f"Running Git-native delta detection between {last_commit[:8]} and {head_commit[:8]}..."
            )
            git_changes = GitScanner.get_git_diff_tree(root_path, last_commit, head_commit)
            gitignore_spec = load_gitignore_spec(root_path)

            to_upsert: list[ScannedFile] = []
            to_delete: list[str] = []

            for status, rel_path in git_changes:
                if status == "D":
                    to_delete.append(rel_path)
                elif status in ("A", "M"):
                    scanned = self._process_single_file(
                        root_path, rel_path, gitignore_spec, cached_data=None
                    )
                    if scanned and scanned.content is not None:
                        scanned.change_type = (
                            FileChangeType.ADDED if status == "A" else FileChangeType.MODIFIED
                        )
                        to_upsert.append(scanned)

            # Persist delta to PostgreSQL manifest
            await ManifestStore.delete_records(to_delete, resolved_repo_id)
            await ManifestStore.upsert_records(to_upsert, resolved_repo_id, head_commit)

            all_hashes = await ManifestStore.load_indexed_hashes(resolved_repo_id)
            result.files_scanned = len(all_hashes)
            result.files_added = sum(1 for f in to_upsert if f.change_type == FileChangeType.ADDED)
            result.files_modified = sum(
                1 for f in to_upsert if f.change_type == FileChangeType.MODIFIED
            )
            result.files_deleted = len(to_delete)
            result.files_unchanged = max(0, len(all_hashes) - len(to_upsert))
            result.indexed_files = to_upsert
            result.deleted_paths = to_delete
            result.elapsed_seconds = round(time.perf_counter() - start_time, 4)
            logger.info(
                f"Git delta completed in {result.elapsed_seconds}s: +{result.files_added} ~{result.files_modified} -{result.files_deleted}"
            )
            return result

        # ------------------------------------------------------------------
        # Standard Path: Initial Scan or Non-Git Full File Walk
        # ------------------------------------------------------------------
        logger.info("Executing parallel file walk and hash verification...")
        gitignore_spec = load_gitignore_spec(root_path)
        existing_manifest = await ManifestStore.load_indexed_hashes(resolved_repo_id)

        all_file_paths: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune excluded and gitignored directories in-place
            dirnames[:] = [
                d
                for d in dirnames
                if not self.sanitizer.should_skip_directory(d)
                and not (
                    gitignore_spec
                    and gitignore_spec.match_file(
                        os.path.relpath(os.path.join(dirpath, d), root_path) + "/"
                    )
                )
            ]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_path)
                if gitignore_spec and gitignore_spec.match_file(rel_path):
                    continue
                all_file_paths.append(rel_path)

        to_upsert = []
        current_seen_paths: set[str] = set()

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [
                pool.submit(
                    self._process_single_file,
                    root_path,
                    rel_p,
                    gitignore_spec,
                    existing_manifest.get(rel_p),
                )
                for rel_p in all_file_paths
            ]
            for f in futures:
                scanned_file = f.result()
                if scanned_file:
                    current_seen_paths.add(scanned_file.file_path)
                    if scanned_file.change_type in (FileChangeType.ADDED, FileChangeType.MODIFIED):
                        to_upsert.append(scanned_file)

        # Detect deleted files
        stored_paths = set(existing_manifest.keys())
        deleted_paths = list(stored_paths - current_seen_paths)

        # Persist manifest updates
        await ManifestStore.delete_records(deleted_paths, resolved_repo_id)
        await ManifestStore.upsert_records(to_upsert, resolved_repo_id, head_commit)

        result.files_scanned = len(current_seen_paths)
        result.files_added = sum(1 for f in to_upsert if f.change_type == FileChangeType.ADDED)
        result.files_modified = sum(
            1 for f in to_upsert if f.change_type == FileChangeType.MODIFIED
        )
        result.files_deleted = len(deleted_paths)
        result.files_unchanged = len(current_seen_paths) - len(to_upsert)
        result.indexed_files = to_upsert
        result.deleted_paths = deleted_paths
        result.elapsed_seconds = round(time.perf_counter() - start_time, 4)

        logger.info(
            f"Scan complete in {result.elapsed_seconds}s: {result.files_scanned} files (+{result.files_added} ~{result.files_modified} -{result.files_deleted})"
        )
        return result

    def _process_single_file(
        self,
        root_path: str,
        rel_path: str,
        gitignore_spec: object,
        cached_data: tuple[str, float | None] | None = None,
    ) -> ScannedFile | None:
        """Inspects, filters, and hashes an individual file."""
        full_path = os.path.join(root_path, rel_path)

        try:
            stat = os.stat(full_path)
            size = stat.st_size
            mtime = stat.st_mtime

            # 1. Enforce size limit
            if size > settings.max_file_size_bytes or size == 0:
                return None

            # 2. Check secret filename patterns
            if self.sanitizer.is_secret_file(rel_path):
                logger.debug(f"Skipping secret file pattern: {rel_path}")
                return None

            # 3. Check minified bundles and lockfiles
            if self.sanitizer.is_minified_or_lockfile(rel_path):
                return None

            # 4. Fast cache check via mtime
            if cached_data:
                cached_hash, cached_mtime = cached_data
                if cached_mtime is not None and cached_mtime == mtime and cached_hash:
                    return ScannedFile(
                        file_path=rel_path,
                        change_type=FileChangeType.UNCHANGED,
                        language=detect_language(rel_path),
                        size_bytes=size,
                        blob_hash=cached_hash,
                        mtime=mtime,
                        content=None,
                    )

            # 5. Read file bytes
            with open(full_path, "rb") as f:
                raw_bytes = f.read()

            # 6. Check binary content
            if self.sanitizer.is_binary(raw_bytes):
                return None

            # 7. Check secret content patterns
            if self.sanitizer.is_secret_file(rel_path, content=raw_bytes):
                logger.warning(f"Excluding file matching secret content signatures: {rel_path}")
                return None

            blob_hash = self._compute_hash(raw_bytes)

            # 8. Check cached content hash
            if cached_data and cached_data[0] == blob_hash:
                return ScannedFile(
                    file_path=rel_path,
                    change_type=FileChangeType.UNCHANGED,
                    language=detect_language(rel_path),
                    size_bytes=size,
                    blob_hash=blob_hash,
                    mtime=mtime,
                    content=None,
                )

            # Decode text content
            text_content = raw_bytes.decode("utf-8", errors="replace")
            change_type = FileChangeType.MODIFIED if cached_data else FileChangeType.ADDED

            return ScannedFile(
                file_path=rel_path,
                change_type=change_type,
                language=detect_language(rel_path),
                size_bytes=size,
                blob_hash=blob_hash,
                mtime=mtime,
                content=text_content,
            )

        except Exception as e:
            logger.debug(f"Error reading {rel_path}: {e}")
            return None
