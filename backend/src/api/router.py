from fastapi import APIRouter

from src.api.endpoints import admin, auth, chats, health, notifications, rag, specialist

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(chats.router, prefix="/chats", tags=["Chats"])
api_router.include_router(
    specialist.router,
    prefix="/specialist",
    tags=["Specialist"],
)
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["Notifications"],
)
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(rag.router, tags=["RAG"])
api_router.include_router(health.router, tags=["Health"])
