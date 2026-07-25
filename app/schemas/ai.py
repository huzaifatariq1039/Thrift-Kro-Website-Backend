from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AIVerificationResponse(BaseModel):
    """Legacy response for the simple image analysis endpoint."""
    is_authentic: bool
    condition_score: int
    detected_category: str
    detected_flaws: List[str]


# --- WebSocket Message Schemas ---

class VerificationFrameMessage(BaseModel):
    """Sent by the frontend: a single base64-encoded JPEG frame from the camera."""
    frame: str  # base64-encoded JPEG


class VerificationStatusMessage(BaseModel):
    """Sent by the backend to the frontend over WebSocket to report progress."""
    phase: str  # "detection" | "liveness" | "matching" | "complete" | "error"
    message: str
    detected_category: Optional[str] = None
    confidence: Optional[float] = None
    liveness_progress: Optional[str] = None  # e.g. "3/5"
    verified: Optional[bool] = None
    similarity_score: Optional[float] = None
    verification_hash: Optional[str] = None


class VerificationResultResponse(BaseModel):
    """REST response for checking a product's verification status."""
    is_verified: bool
    similarity_score: Optional[float] = None
    detected_category: Optional[str] = None
    verification_hash: Optional[str] = None
    verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True
