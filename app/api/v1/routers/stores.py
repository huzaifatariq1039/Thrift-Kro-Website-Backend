from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.schemas.store import StoreRankingResponse
from app.models.user import SellerProfile
from app.api.deps import get_db

router = APIRouter()

@router.get("/ranking", response_model=List[StoreRankingResponse])
def get_store_rankings(limit: int = 10, db: Session = Depends(get_db)):
    """
    Get top stores ranked by rating and review count.
    """
    ranked_stores = db.query(SellerProfile).order_by(
        SellerProfile.rating.desc(),
        SellerProfile.review_count.desc()
    ).limit(limit).all()
    
    return ranked_stores
