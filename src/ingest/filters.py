"""Security sanitization, exclusion rules, and gitignore evaluation."""

import fnmatch
import os
import re
from typing import ClassVar

import pathspec

# Sensitive file patterns that MUST NEVER be indexed into vector stores
SECRET_FILENAME_PATTERNS: list[str] = [
    ".env*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "*.crt",
    "*.pfx",
    "*.p12",
    "*.secret*",
    "credentials.json",
    "service_account*.json",
    "client_secret*.json",
    "*_rsa",
    "token.json",
    "auth.json",
]

# Sensitive content signatures (regex)
SECRET_CONTENT_PATTERNS: list[re.Pattern[bytes]] = [
    re.compile(b"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(b"-----BEGIN PRIVATE KEY-----"),
    re.compile(b"AKIA[0-9A-Z]{16}"),  # AWS Access Key ID
    re.compile(b"ghp_[0-9a-zA-Z]{36}"),  # GitHub Personal Access Token
]

# Minified / Bundle / Lockfile patterns to ignore
MINIFIED_OR_LOCK_PATTERNS: list[str] = [
    "*.min.js",
    "*.min.css",
    "*.map",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
    "composer.lock",
]

# Hard-coded directory exclusions
EXCLUDED_DIRECTORIES: set[str] = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".next",
    ".nuxt",
    "coverage",
    "htmlcov",
}


class SecuritySanitizer:
    """Security and relevance filter for source files."""

    MAX_FILE_BYTES: ClassVar[int] = 1_048_576  # 1 MB default ceiling

    @staticmethod
    def is_secret_file(rel_path: str, content: bytes | None = None) -> bool:
        """Checks if a file name or its content matches secret/credential patterns."""
        filename = os.path.basename(rel_path).lower()

        for pattern in SECRET_FILENAME_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True

        if content:
            for regex in SECRET_CONTENT_PATTERNS:
                if regex.search(content):
                    return True

        return False

    @staticmethod
    def is_binary(data: bytes) -> bool:
        """Fast binary probe: checks for null bytes or excessive non-printable characters."""
        if not data:
            return False
        # Null bytes indicate binary executable, image, or compressed data
        if b"\x00" in data[:8192]:
            return True

        # Check non-text byte ratio in sample
        sample = data[:1024]
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
        non_text_count = sum(byte not in text_chars for byte in sample)
        return (non_text_count / len(sample)) > 0.30

    @staticmethod
    def is_minified_or_lockfile(rel_path: str, data: bytes | None = None) -> bool:
        """Checks if a file is a bundle, source map, or package lockfile."""
        filename = os.path.basename(rel_path).lower()

        for pattern in MINIFIED_OR_LOCK_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True

        if data:
            # Check for extraordinarily long average lines (minified JS/CSS)
            lines = data[:4096].split(b"\n")
            if lines and any(len(line) > 1000 for line in lines):
                return True

        return False

    @staticmethod
    def should_skip_directory(dir_name: str) -> bool:
        """Returns True if directory is a standard build artifact or cache folder."""
        return dir_name in EXCLUDED_DIRECTORIES or dir_name.startswith(".")


def load_gitignore_spec(root_path: str) -> pathspec.PathSpec | None:
    """Loads and compiles all .gitignore files starting from root_path."""
    gitignore_path = os.path.join(root_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None

    try:
        with open(gitignore_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except Exception:
        return None
