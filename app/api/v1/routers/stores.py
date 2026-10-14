from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.schemas.store import StoreRankingResponse
from app.models.user import SellerProfile, VerificationStatusEnum
from app.api.deps import get_db

router = APIRouter()


@router.get("/ranking", response_model=List[StoreRankingResponse])
def get_store_rankings(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get top stores ranked by rating and review count.
    """
    ranked_stores = (
        db.query(SellerProfile)
        .filter(
            SellerProfile.verification_status == VerificationStatusEnum.APPROVED,
            SellerProfile.review_count > 0,
        )
        .order_by(
            SellerProfile.rating.desc(),
            SellerProfile.review_count.desc(),
            SellerProfile.created_at.asc(),
        )
        .limit(limit)
        .all()
    )

    return ranked_stores
