"""Data models for the ingestion and manifest engine."""

from enum import StrEnum

from pydantic import BaseModel, Field


class FileChangeType(StrEnum):
    """Type of change detected for a file."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"


class ScannedFile(BaseModel):
    """Represents a discovered and processed source file."""

    file_path: str
    change_type: FileChangeType
    language: str
    size_bytes: int
    blob_hash: str
    mtime: float
    content: str | None = None


class IngestionResult(BaseModel):
    """Summary of a completed ingestion operation."""

    repo_id: str
    source_path: str
    commit_sha: str | None = None
    files_scanned: int = 0
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    files_unchanged: int = 0
    indexed_files: list[ScannedFile] = Field(default_factory=list)
    deleted_paths: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
