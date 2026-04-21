from fastapi import FastAPI

from app.features.ai_chat.router import router as ai_chat_router
from app.features.articles.router import router as articles_router
from app.features.auth.router import router as auth_router
from app.features.system.router import router as system_router

app = FastAPI(
    title="Verida API",
    description="Бэкенд для scientific_chat_app: чат, заметки, закрепление, профиль.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.include_router(system_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(ai_chat_router, prefix="/api")
app.include_router(articles_router, prefix="/api")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Лёгкий health для балансировщиков и docker healthcheck."""
    return {"status": "ok"}
