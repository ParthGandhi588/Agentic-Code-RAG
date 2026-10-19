"""Unit tests for security filtering, binary checks, and language detection."""

from src.ingest.detector import detect_language
from src.ingest.filters import SecuritySanitizer


def test_language_detection() -> None:
    assert detect_language("src/main.py") == "python"
    assert detect_language("app/index.ts") == "typescript"
    assert detect_language("components/Button.tsx") == "typescript"
    assert detect_language("server/main.go") == "go"
    assert detect_language("src/lib.rs") == "rust"
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("Makefile") == "makefile"
    assert detect_language("styles.css") == "css"
    assert detect_language("data.json") == "json"
    assert detect_language("unknown_file.xyz123") == "unknown"


def test_secret_file_filtering() -> None:
    sanitizer = SecuritySanitizer()

    # Secret filenames
    assert sanitizer.is_secret_file(".env") is True
    assert sanitizer.is_secret_file(".env.production") is True
    assert sanitizer.is_secret_file("id_rsa") is True
    assert sanitizer.is_secret_file("id_ed25519") is True
    assert sanitizer.is_secret_file("server.key") is True
    assert sanitizer.is_secret_file("cert.pem") is True
    assert sanitizer.is_secret_file("service_account_prod.json") is True
    assert sanitizer.is_secret_file("credentials.json") is True

    # Safe filenames
    assert sanitizer.is_secret_file("main.py") is False
    assert sanitizer.is_secret_file("environment.ts") is False
    assert sanitizer.is_secret_file("key_handler.py") is False
    assert sanitizer.is_secret_file("app.json") is False


def test_secret_content_filtering() -> None:
    sanitizer = SecuritySanitizer()

    rsa_key = (
        b"-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
    )
    assert sanitizer.is_secret_file("innocent.txt", content=rsa_key) is True

    safe_content = b"def authenticate(user_token: str) -> bool:\n    return True\n"
    assert sanitizer.is_secret_file("auth.py", content=safe_content) is False


def test_binary_detection() -> None:
    sanitizer = SecuritySanitizer()

    # Null bytes indicate binary
    binary_data = b"GIF89a\x00\x01\x00\x01\x00\x80\x00"
    assert sanitizer.is_binary(binary_data) is True

    # Normal text
    text_data = b"print('Hello, World!')\n"
    assert sanitizer.is_binary(text_data) is False


def test_minified_and_lockfile_filtering() -> None:
    sanitizer = SecuritySanitizer()

    assert sanitizer.is_minified_or_lockfile("bundle.min.js") is True
    assert sanitizer.is_minified_or_lockfile("styles.min.css") is True
    assert sanitizer.is_minified_or_lockfile("package-lock.json") is True
    assert sanitizer.is_minified_or_lockfile("yarn.lock") is True
    assert sanitizer.is_minified_or_lockfile("uv.lock") is True
    assert sanitizer.is_minified_or_lockfile("app.js") is False
