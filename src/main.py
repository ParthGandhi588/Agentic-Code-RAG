"""FastAPI Application Entrypoint for Agentic-Code-RAG."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.errors import (
    APIError,
    api_error_handler,
    generic_exception_handler,
    validation_error_handler,
)
from src.api.job_manager import JobManager
from src.api.job_store import JobStore
from src.api.routers.chat import router as chat_router
from src.api.routers.jobs import router as jobs_router
from src.api.routers.repos import router as repos_router
from src.core.config import get_settings
from src.core.logger import setup_logger
from src.ingest.manifest import ManifestStore
from src.parser.graph_store import CodeGraphStore
from src.retrieval.store import VectorStore

settings = get_settings()
logger = setup_logger("agentic-api", level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for application startup and shutdown events."""
    logger.info("Initializing Agentic-Code-RAG backend...")
    logger.info(f"Environment: {settings.app_env} | LLM Provider: {settings.llm_provider}")

    # Verify and initialize database schemas across all modules
    await ManifestStore.init_schema()
    await CodeGraphStore.init_schema()
    await VectorStore.init_schema()
    await JobStore.init_schema()

    yield
    logger.info("Shutting down Agentic-Code-RAG backend...")
    await JobManager.cancel_all()


app = FastAPI(
    title="Agentic-Code-RAG API",
    description="Next-Generation Autonomous Code Intelligence Engine API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register RFC 7807 Problem Details exception handlers
app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)

# Mount API Routers
app.include_router(repos_router)
app.include_router(jobs_router)
app.include_router(chat_router)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Basic service healthcheck endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "env": settings.app_env,
    }


# Mount production frontend SPA build if available
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
