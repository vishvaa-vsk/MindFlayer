"""TestCortex: Context-aware test intelligence engine."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

# Create FastAPI app
app = FastAPI(
    title="TestCortex",
    description="Context-aware test intelligence engine",
    version="0.1.0",
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
        "name": "TestCortex",
        "version": "0.1.0",
        "message": "Context-aware test intelligence engine",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
