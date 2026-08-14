import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import SessionLocal
import app.crud.user as crud_user
from app.schemas.user import UserCreate

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FastAPI Backend for Thrift Kro E-Commerce Marketplace",
    version="1.0.0"
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

app.include_router(api_router, prefix="/api/v1")

@app.on_event("startup")
def startup_event():
    # Auto-create all tables if they don't exist (essential for fresh deployments like Railway)
    from app.core.database import engine, Base
    # Import all models so they are registered with Base.metadata
    import app.models.user  # noqa
    import app.models.product  # noqa
    import app.models.order  # noqa
    import app.models.review  # noqa
    import app.models.message  # noqa
    import app.models.shopping  # noqa
    import app.models.support  # noqa
    import app.models.verification  # noqa
    import app.models.seller_verification  # noqa
    Base.metadata.create_all(bind=engine)
    print("Database tables ensured.")

    db = SessionLocal()
    try:
        admin_email = "admin@thriftkro.pk"
        admin = crud_user.get_user_by_email(db, email=admin_email)
        if not admin:
            crud_user.create_user(db, UserCreate(
                email=admin_email,
                full_name="System Admin",
                password="Admin@123",
                role="ADMIN"
            ))
            print("Admin user provisioned successfully.")
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "Welcome to Thrift Kro API"}
