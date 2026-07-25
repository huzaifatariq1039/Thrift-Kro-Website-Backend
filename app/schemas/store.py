from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.models.user import VerificationStatusEnum

class StoreRankingResponse(BaseModel):
    user_id: UUID
    shop_name: str
    description: Optional[str]
    is_verified: bool
    verification_status: VerificationStatusEnum = VerificationStatusEnum.UNVERIFIED
    rating: float
    review_count: int

    class Config:
        from_attributes = True
