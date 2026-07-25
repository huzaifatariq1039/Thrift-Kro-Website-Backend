from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.schemas.review import ReviewCreate, ReviewResponse
from app.models.user import User
import app.crud.review as crud_review
from app.api.deps import get_db, get_current_active_user

router = APIRouter()

@router.post("/", response_model=ReviewResponse)
def submit_review(review: ReviewCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return crud_review.create_review(
        db=db, 
        review=review, 
        buyer_id=current_user.id, 
        hex_code=current_user.hex_code
    )

@router.get("/product/{product_id}", response_model=List[ReviewResponse])
def get_product_reviews(product_id: UUID, db: Session = Depends(get_db)):
    return crud_review.get_reviews_by_product(db=db, product_id=product_id)
