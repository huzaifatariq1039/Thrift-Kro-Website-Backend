"""CRUD operations for verified-purchase product reviews."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.review import Review
from app.schemas.review import ReviewCreate
from app.services.review_integrity import create_verified_review


def create_review(
    db: Session,
    review: ReviewCreate,
    buyer_id: UUID,
    hex_code: str | None = None,
) -> Review:
    """Create a review only when an immutable fulfilled order item proves eligibility."""
    return create_verified_review(db, review, buyer_id)


def get_reviews_by_product(db: Session, product_id: UUID) -> List[Review]:
    """Return trusted reviews only, newest first."""
    return (
        db.query(Review)
        .filter(
            Review.product_id == product_id,
            Review.is_verified_purchase.is_(True),
        )
        .order_by(Review.created_at.desc(), Review.id.desc())
        .all()
    )


def get_review(db: Session, review_id: UUID) -> Optional[Review]:
    """Get a trusted review by ID."""
    return (
        db.query(Review)
        .filter(
            Review.id == review_id,
            Review.is_verified_purchase.is_(True),
        )
        .first()
    )
