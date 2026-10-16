from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.schemas.review import ReviewCreate, ReviewResponse
from app.models.user import User
import app.crud.review as crud_review
from app.api.deps import get_db, get_current_buyer
from app.api.pagination import PageLimit, PageOffset
from app.services.review_integrity import (
    DuplicateReviewError,
    ProductNotFoundError,
    ReviewEligibilityError,
    ReviewIntegrityError,
)

router = APIRouter()


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def submit_review(
    review: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    try:
        return crud_review.create_review(
            db=db,
            review=review,
            buyer_id=current_user.id,
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewEligibilityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DuplicateReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/product/{product_id}", response_model=List[ReviewResponse])
def get_product_reviews(
    product_id: UUID,
    skip: PageOffset = 0,
    limit: PageLimit = 50,
    db: Session = Depends(get_db),
):
    return crud_review.get_reviews_by_product(
        db=db,
        product_id=product_id,
        skip=skip,
        limit=limit,
    )
