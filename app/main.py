"""FastAPI main application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.logging import logger
from app.db.connection import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager initializing database on startup."""
    logger.info("Initializing database schema...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down AI Voice Agent server.")


app = FastAPI(
    title="AI Voice Appointment Agent",
    description="Low-latency telephony voice agent for dental appointment bookings via Plivo",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(webhooks_router)
app.include_router(ws_router)

