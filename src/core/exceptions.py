"""Domain-specific custom exceptions for Agentic-Code-RAG."""


class AgenticRAGException(Exception):
    """Base exception for all Agentic-Code-RAG domain errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(AgenticRAGException):
    """Raised when application or environment configuration is invalid."""


class RepositoryNotFoundError(AgenticRAGException):
    """Raised when a requested repository or source path does not exist."""


class IngestionError(AgenticRAGException):
    """Raised when a repository scanning or parsing operation fails."""


class IndexingError(AgenticRAGException):
    """Raised when database or vector store insertion fails."""


class LLMProviderError(AgenticRAGException):
    """Raised when communication with an LLM provider fails."""
