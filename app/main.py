import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.observability import ObservabilityMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup is deliberately read-only; shutdown releases pooled connections."""
    yield
    engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Thrift Kro E-Commerce Marketplace",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
raw_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").strip()

if raw_allowed_origins == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed_origins = [origin.strip() for origin in raw_allowed_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(ObservabilityMiddleware)

app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Welcome to Thrift Kro API"}
