"""Programming language and configuration file detection."""

import os

EXTENSION_MAP: dict[str, str] = {
    # Systems & Compiled
    ".py": "python",
    ".pyi": "python",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".swift": "swift",
    # Web & Scripting
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".php": "php",
    ".rb": "ruby",
    ".lua": "lua",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    # Markup, Docs & Data
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".sql": "sql",
    ".md": "markdown",
    ".rst": "rst",
    ".graphql": "graphql",
    ".proto": "protobuf",
}

EXACT_FILENAME_MAP: dict[str, str] = {
    "dockerfile": "dockerfile",
    "containerfile": "dockerfile",
    "makefile": "makefile",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "vagrantfile": "ruby",
    "cmakelists.txt": "cmake",
}


def detect_language(file_path: str) -> str:
    """Detects programming language from file extension, name, or shebang."""
    base_name = os.path.basename(file_path).lower()

    if base_name in EXACT_FILENAME_MAP:
        return EXACT_FILENAME_MAP[base_name]

    ext = os.path.splitext(base_name)[1]
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    return "unknown"
