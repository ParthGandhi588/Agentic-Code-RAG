"""FastAPI Application Entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.logger import setup_logger

settings = get_settings()
logger = setup_logger("agentic-api", level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for application startup and shutdown events."""
    logger.info("Initializing Agentic-Code-RAG backend...")
    logger.info(f"Environment: {settings.app_env} | LLM Provider: {settings.llm_provider}")
    yield
    logger.info("Shutting down Agentic-Code-RAG backend...")


app = FastAPI(
    title="Agentic-Code-RAG API",
    description="Next-Generation Autonomous Code Intelligence Engine API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Basic service healthcheck endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "env": settings.app_env,
    }
