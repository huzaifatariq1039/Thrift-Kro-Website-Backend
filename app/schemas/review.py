from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class ReviewCreate(BaseModel):
    product_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    product_id: UUID
    rating: int
    comment: Optional[str]
    is_verified_purchase: bool
    created_at: datetime

    class Config:
        from_attributes = True
