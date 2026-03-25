import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.api.router import api_router
from src.core.config import settings, validate_settings
from src.core.logging import configure_logging
from src.db.bootstrap import prepare_database

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers into every response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        return response


async def _purge_expired_tokens() -> None:
    """Delete stale reset and verification tokens during application startup."""
    from datetime import datetime, timedelta, timezone

    from src.db.session import SessionLocal

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for table_name in ["password_reset_tokens", "email_verification_tokens"]:
            try:
                from sqlalchemy import text

                db.execute(
                    text(f"DELETE FROM {table_name} WHERE created_at < :cutoff"),
                    {"cutoff": cutoff},
                )
            except Exception:
                pass
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to purge expired tokens on startup")
    finally:
        db.close()


async def _cleanup_stale_generations() -> None:
    """Reset messages left in generating state after an unclean shutdown."""
    from src.db.models import Message
    from src.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = (
            db.query(Message)
            .filter(Message.is_generating == True)  # noqa: E712
            .update(
                {
                    "is_generating": False,
                    "content": "Generation interrupted. Please try again.",
                }
            )
        )
        db.commit()
        if count:
            logger.info("Reset %d stale is_generating messages on startup", count)
    except Exception:
        db.rollback()
        logger.exception("Failed to clean up stale generating messages")
    finally:
        db.close()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Run one-time startup maintenance before serving requests."""
    await _purge_expired_tokens()
    await _cleanup_stale_generations()
    yield


def create_app() -> FastAPI:
    configure_logging()
    validate_settings()
    prepare_database()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Clinical RAG Backend for Neurology & Rheumatology Support",
        version=settings.PROJECT_VERSION,
        lifespan=_lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )
    app.include_router(api_router)

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"status": "Ambience Backend Running"}

    return app
