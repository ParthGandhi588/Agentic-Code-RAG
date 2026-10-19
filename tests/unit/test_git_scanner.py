"""Unit tests for Git-native plumbing operations."""

import subprocess
import tempfile

from src.ingest.git_scanner import GitScanner


def test_git_repo_detection_and_diff_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Non-git folder initially
        assert GitScanner.is_git_repo(tmp_dir) is False

        # 2. Initialize Git
        subprocess.run(["git", "init", tmp_dir], check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp_dir, "config", "user.name", "Tester"], check=True)
        subprocess.run(["git", "-C", tmp_dir, "config", "user.email", "test@test.com"], check=True)
        assert GitScanner.is_git_repo(tmp_dir) is True

        # 3. Commit 1: add file1.py
        file1 = f"{tmp_dir}/file1.py"
        with open(file1, "w") as f:
            f.write("def foo(): return 1\n")
        subprocess.run(["git", "-C", tmp_dir, "add", "file1.py"], check=True)
        subprocess.run(["git", "-C", tmp_dir, "commit", "-m", "commit 1"], check=True)

        commit1 = GitScanner.get_head_commit(tmp_dir)
        assert commit1 is not None
        assert len(commit1) == 40

        # 4. Commit 2: modify file1.py, add file2.py
        with open(file1, "w") as f:
            f.write("def foo(): return 2\n")
        file2 = f"{tmp_dir}/file2.py"
        with open(file2, "w") as f:
            f.write("def bar(): return 'hello'\n")
        subprocess.run(["git", "-C", tmp_dir, "add", "file1.py", "file2.py"], check=True)
        subprocess.run(["git", "-C", tmp_dir, "commit", "-m", "commit 2"], check=True)

        commit2 = GitScanner.get_head_commit(tmp_dir)
        assert commit2 is not None
        assert commit1 != commit2

        # 5. Check git diff-tree delta between commit1 and commit2
        diff = GitScanner.get_git_diff_tree(tmp_dir, commit1, commit2)
        diff_dict = {path: status for status, path in diff}

        assert diff_dict.get("file1.py") == "M"
        assert diff_dict.get("file2.py") == "A"
