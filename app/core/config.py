import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Thrift Kro Backend"
    SQLALCHEMY_DATABASE_URI: str = os.environ["DATABASE_URL"]
    SECRET_KEY: str = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
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
