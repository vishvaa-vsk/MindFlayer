"""MindFlayer: AI-powered test intelligence engine."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mindflayer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    settings = get_settings()
    logger.info(f"🧠 {settings.app_name} v{settings.app_version} starting...")
    logger.info(f"   Parsing model:    {settings.parsing_model}")
    logger.info(f"   Generation model: {settings.generation_model}")
    logger.info(f"   API key:          {'✅ configured' if settings.has_api_key else '❌ not set'}")
    logger.info(f"   CORS origins:     {settings.cors_origins}")
    yield
    logger.info(f"🧠 {settings.app_name} shutting down.")


# Create FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="AI-powered test intelligence engine that plans missing API tests from requirements and generates executable test code.",
    version=settings.app_version,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api", tags=["tests"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "AI-powered test intelligence engine",
        "docs": "/docs",
        "api": "/api",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
