"""Unit tests for AST-aware code chunking."""

from src.parser.models import CodeSymbol, SymbolKind
from src.retrieval.chunker import CodeChunker


def test_ast_symbol_chunking() -> None:
    code = """class AuthService:
    def login(self):
        pass

def register_user():
    return True
"""
    symbols = [
        CodeSymbol(
            name="AuthService",
            qualified_name="AuthService",
            kind=SymbolKind.CLASS,
            file_path="src/auth.py",
            start_line=1,
            end_line=3,
            signature="class AuthService:",
            language="python",
        ),
        CodeSymbol(
            name="register_user",
            qualified_name="register_user",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth.py",
            start_line=5,
            end_line=6,
            signature="def register_user():",
            language="python",
        ),
    ]

    chunker = CodeChunker()
    chunks = chunker.chunk_file("src/auth.py", code, "python", symbols=symbols)

    assert len(chunks) >= 2
    # Verify symbol boundary preservation
    auth_chunk = next(c for c in chunks if "AuthService" in c.content)
    assert auth_chunk.start_line == 1
    assert auth_chunk.end_line == 3
    assert "--- File: src/auth.py:1-3" in auth_chunk.content

    reg_chunk = next(c for c in chunks if "register_user" in c.content)
    assert reg_chunk.start_line == 5
    assert reg_chunk.end_line == 6
