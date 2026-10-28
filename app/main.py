"""FastAPI main application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.logging import logger
from app.db.connection import init_db

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
    description="Low-latency conversational voice agent with direct browser Web Audio transport and LLM tool calling",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(ws_router)


@app.get("/", include_in_schema=False)
@app.get("/call", include_in_schema=False)
async def serve_call_interface():
    """Serves the static Web Audio browser client."""
    index_file = STATIC_DIR / "index.html"
    return FileResponse(index_file)


# Mount static directory for assets if needed
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
