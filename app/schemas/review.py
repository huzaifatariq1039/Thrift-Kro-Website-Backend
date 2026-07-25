from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class ReviewCreate(BaseModel):
    product_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

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
