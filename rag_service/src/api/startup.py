from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import FastAPI

from ..config import cloud_llm_config, local_llm_config, routing_config
from ..generation.client import ProviderName
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


async def warmup_model(provider: ProviderName = "local") -> None:
    from ..generation.client import warmup_model as _warmup_model

    await _warmup_model(provider=provider)


def load_embedder() -> Any:
    from ..ingestion.embed import load_embedder as _load_embedder

    return _load_embedder()


def get_vector_dim(model: Any) -> int:
    from ..ingestion.embed import get_vector_dim as _get_vector_dim

    return _get_vector_dim(model)


def init_db(vector_dim: int) -> None:
    from ..retrieval.vector_store import init_db as _init_db

    _init_db(vector_dim=vector_dim)


def ensure_schema() -> None:
    """Create pgvector extension and tables if missing."""
    try:
        init_db(vector_dim=get_embedding_dimension())
        logger.info("Database schema ready (chunks/documents).")
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to initialize database schema.")
        raise RuntimeError("Database schema initialization failed") from exc


async def warmup_ollama() -> None:
    """Pre-load the selected generation provider on service startup."""
    if routing_config.force_cloud_llm:
        logger.info(
            "Cloud-only mode enabled. Using cloud model '%s'.",
            cloud_llm_config.model,
        )
        await warmup_model(provider="cloud")
        return

    logger.info("Warming up local model '%s'...", local_llm_config.model)
    await warmup_model()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    del app
    get_embedding_dimension()
    ensure_schema()
    await warmup_ollama()
    yield


@lru_cache(maxsize=1)
def get_embedding_model() -> Any:
    logger.info("Loading embedding model...")
    model = load_embedder()
    logger.info("Embedding model loaded. dim=%s", get_vector_dim(model))
    return model


@lru_cache(maxsize=1)
def get_embedding_dimension() -> int:
    return get_vector_dim(get_embedding_model())
