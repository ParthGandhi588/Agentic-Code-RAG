"""Unit tests for IngestionEngine file processing and security exclusion."""

import tempfile

import pytest

from src.ingest.engine import IngestionEngine
from src.ingest.models import FileChangeType


@pytest.mark.asyncio
async def test_ingest_local_folder_with_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Valid code file
        with open(f"{tmp_dir}/main.py", "w") as f:
            f.write("def run(): pass\n")

        # Nested valid file
        import os

        os.makedirs(f"{tmp_dir}/src", exist_ok=True)
        with open(f"{tmp_dir}/src/app.py", "w") as f:
            f.write("class App: pass\n")

        # Secret file (must be skipped)
        with open(f"{tmp_dir}/.env", "w") as f:
            f.write("SECRET_KEY=supersecret\n")

        # Binary file (must be skipped)
        with open(f"{tmp_dir}/image.png", "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

        # Minified file (must be skipped)
        with open(f"{tmp_dir}/bundle.min.js", "w") as f:
            f.write("console.log('min');")

        engine = IngestionEngine()
        result = await engine.ingest(tmp_dir, repo_id="test_repo")

        assert result.repo_id == "test_repo"
        assert result.files_scanned == 2

        file_paths = [f.file_path for f in result.indexed_files]
        assert "main.py" in file_paths
        assert "src/app.py" in file_paths
        assert ".env" not in file_paths
        assert "image.png" not in file_paths
        assert "bundle.min.js" not in file_paths

        for f in result.indexed_files:
            assert f.change_type == FileChangeType.ADDED
            assert f.blob_hash is not None
            assert f.content is not None
