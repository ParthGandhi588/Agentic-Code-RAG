"""Git plumbing operations for lightning-fast delta detection."""

import os
import shutil
import subprocess

from src.core.logger import setup_logger

logger = setup_logger("agentic-git-scanner")


class GitScanner:
    """High-performance Git operations using native git plumbing."""

    @staticmethod
    def is_git_repo(path: str) -> bool:
        """Checks if a directory contains a valid Git repository."""
        git_dir = os.path.join(path, ".git")
        return os.path.isdir(git_dir) or os.path.isfile(git_dir)

    @staticmethod
    def get_head_commit(repo_path: str) -> str | None:
        """Returns the current HEAD commit hash (40 chars) or None if unavailable."""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Could not retrieve HEAD commit for {repo_path}: {e}")
            return None

    @staticmethod
    def get_git_diff_tree(
        repo_path: str, old_commit: str, new_commit: str
    ) -> list[tuple[str, str]]:
        """Runs 'git diff-tree' between two commits to detect changes in milliseconds.

        Returns list of (status, file_path) where status is 'A', 'M', or 'D'.
        """
        try:
            cmd = [
                "git",
                "-C",
                repo_path,
                "diff-tree",
                "-r",
                "--no-commit-id",
                "--name-status",
                old_commit,
                new_commit,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            changes: list[tuple[str, str]] = []
            for line in result.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    status, rel_path = parts[0][0], parts[1].strip()
                    changes.append((status, rel_path))
            return changes
        except Exception as e:
            logger.warning(f"git diff-tree failed ({old_commit}..{new_commit}): {e}")
            return []

    @staticmethod
    def clone_repo(url: str, target_dir: str, depth: int = 1) -> str:
        """Safely clones a remote Git repository with shallow history."""
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
        os.makedirs(target_dir, exist_ok=True)

        logger.info(f"Cloning {url} into {target_dir} (depth={depth})...")
        cmd = ["git", "clone", "--depth", str(depth), url, target_dir]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
        return target_dir
