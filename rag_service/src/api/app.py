from fastapi import FastAPI

from src.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Ambience RAG", version="1.0.0")
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
