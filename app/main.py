import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Thrift Kro E-Commerce Marketplace",
    version="1.0.0"
)

# CORS configuration reading from ALLOWED_ORIGINS env variable with '*' fallback
raw_allowed_origins = os.getenv("ALLOWED_ORIGINS", "").strip()

if raw_allowed_origins:
    allowed_origins = [origin.strip() for origin in raw_allowed_origins.split(",") if origin.strip()]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True if allowed_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "Welcome to Thrift Kro API"}
