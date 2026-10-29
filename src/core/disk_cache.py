import json
import os
from pathlib import Path
from typing import Any

from src.core.logger import setup_logger

logger = setup_logger("agentic-disk-cache")
CACHE_DIR = Path(".rag_cache")


def ensure_cache_dir() -> Path:
    """Ensures .rag_cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def is_test_environment(cache_key: str) -> bool:
    """Checks if currently in test mode or dealing with test artifacts."""
    return os.environ.get("APP_ENV") == "testing" or cache_key.startswith("test_")


def save_cache(cache_key: str, data: Any) -> None:
    """Saves serializable data to disk cache."""
    if is_test_environment(cache_key):
        return
    try:
        ensure_cache_dir()
        file_path = CACHE_DIR / f"{cache_key}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        logger.debug(f"Saved disk cache: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to save disk cache for {cache_key}: {e}")


def load_cache(cache_key: str) -> Any | None:
    """Loads serializable data from disk cache if present."""
    if is_test_environment(cache_key):
        return None
    try:
        file_path = CACHE_DIR / f"{cache_key}.json"
        if file_path.is_file():
            with file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Failed to read disk cache for {cache_key}: {e}")
    return None
