from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class VerificationResultResponse(BaseModel):
    """Evidence-backed product verification status."""
    is_verified: bool
    similarity_score: Optional[float] = None
    detected_category: Optional[str] = None
    verification_hash: Optional[str] = None
    verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True
