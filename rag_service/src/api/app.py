from fastapi import FastAPI

from .ask_routes import router as ask_router
from .routes import router
from .startup import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ambience Med42 RAG Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(ask_router)
    return app


app = create_app()
