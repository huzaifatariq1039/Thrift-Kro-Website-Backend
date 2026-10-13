import os
import hashlib
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL environment variable is strictly required.")


_EXPOSED_SECRET_KEY_HASHES = {
    "570dad43de1af4c925f92c16a68a50936da42b7dd6fdeb24850507a1199aac89",
}


def validate_secret_key(value: str | None) -> str:
    """Require an explicit, sufficiently strong, non-default JWT signing key."""
    if not value:
        raise ValueError("SECRET_KEY environment variable is strictly required.")
    if len(value) < 32:
        raise ValueError("SECRET_KEY must contain at least 32 characters.")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    if digest in _EXPOSED_SECRET_KEY_HASHES:
        raise ValueError("SECRET_KEY uses a known exposed value and must be rotated.")
    return value


secret_key = validate_secret_key(os.getenv("SECRET_KEY"))


class Settings(BaseSettings):
    PROJECT_NAME: str = "Thrift Kro Backend"
    SQLALCHEMY_DATABASE_URI: str = db_url
    SECRET_KEY: str = secret_key
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "")
    
    # AI Verification settings
    YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
    CLIP_MODEL: str = os.getenv("CLIP_MODEL", "ViT-B-32")
    CLIP_PRETRAINED: str = os.getenv("CLIP_PRETRAINED", "openai")
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))
    LIVENESS_FRAMES_REQUIRED: int = int(os.getenv("LIVENESS_FRAMES_REQUIRED", "5"))
    LIVENESS_MOVEMENT_THRESHOLD: float = float(os.getenv("LIVENESS_MOVEMENT_THRESHOLD", "15.0"))
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.5"))

settings = Settings()
