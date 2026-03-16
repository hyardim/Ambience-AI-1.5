from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.core.config import settings
from src.core.logging import configure_logging
from src.db.bootstrap import prepare_database


def create_app() -> FastAPI:
    configure_logging()
    prepare_database()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Clinical RAG Backend for Neurology & Rheumatology Support",
        version=settings.PROJECT_VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"status": "Ambience Backend Running"}

    return app
