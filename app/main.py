from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.http_security import (
    load_http_security_policy,
    unhandled_exception_response,
)
from app.core.observability import ObservabilityMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup is deliberately read-only; shutdown releases pooled connections."""
    yield
    engine.dispose()

http_security = load_http_security_policy()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Thrift Kro E-Commerce Marketplace",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if http_security.docs_enabled else None,
    redoc_url="/redoc" if http_security.docs_enabled else None,
    openapi_url="/openapi.json" if http_security.docs_enabled else None,
)
app.add_exception_handler(Exception, unhandled_exception_response)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(http_security.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Request-ID",
    ],
)

app.add_middleware(ObservabilityMiddleware)

app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Welcome to Thrift Kro API"}
