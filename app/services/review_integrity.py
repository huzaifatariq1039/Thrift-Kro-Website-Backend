from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import CheckoutOrder, OrderItem, OrderStatusEnum, SellerOrder
from app.models.product import Product
from app.models.review import Review
from app.models.user import SellerProfile
from app.schemas.review import ReviewCreate


FULFILLED_REVIEW_STATUSES = (
    OrderStatusEnum.DELIVERED,
    OrderStatusEnum.COMPLETED,
    OrderStatusEnum.COMPLETED_PAYOUT,
)


class ReviewIntegrityError(ValueError):
    pass


class ProductNotFoundError(ReviewIntegrityError):
    pass


class ReviewEligibilityError(ReviewIntegrityError):
    pass


class DuplicateReviewError(ReviewIntegrityError):
    pass


def _recalculate_seller_rating(
    db: Session,
    seller_profile: SellerProfile,
    seller_id: UUID,
) -> None:
    review_count, average_rating = (
        db.query(func.count(Review.id), func.avg(Review.rating))
        .join(Product, Product.id == Review.product_id)
        .filter(
            Product.seller_id == seller_id,
            Review.is_verified_purchase.is_(True),
        )
        .one()
    )
    seller_profile.review_count = int(review_count or 0)
    if average_rating is None:
        seller_profile.rating = 0.0
    else:
        seller_profile.rating = float(
            Decimal(str(average_rating)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )


def create_verified_review(
    db: Session,
    review: ReviewCreate,
    buyer_id: UUID,
) -> Review:
    """Create one review backed by a fulfilled order item and refresh its seller aggregate."""
    try:
        product = db.query(Product).filter(Product.id == review.product_id).one_or_none()
        if product is None:
            raise ProductNotFoundError("Product not found")

        order_item = (
            db.query(OrderItem)
            .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
            .join(CheckoutOrder, CheckoutOrder.id == SellerOrder.checkout_order_id)
            .filter(
                CheckoutOrder.buyer_id == buyer_id,
                OrderItem.product_id_snapshot == review.product_id,
                SellerOrder.status.in_(FULFILLED_REVIEW_STATUSES),
            )
            .order_by(OrderItem.created_at.asc(), OrderItem.id.asc())
            .with_for_update(of=OrderItem)
            .first()
        )
        if order_item is None:
            raise ReviewEligibilityError(
                "A delivered or completed purchase is required to review this product"
            )

        existing_review = (
            db.query(Review)
            .filter(
                Review.buyer_id == buyer_id,
                Review.product_id == review.product_id,
            )
            .first()
        )
        if existing_review is not None:
            raise DuplicateReviewError("You have already reviewed this product")

        seller_profile = (
            db.query(SellerProfile)
            .filter(SellerProfile.user_id == product.seller_id)
            .with_for_update()
            .one_or_none()
        )
        if seller_profile is None:
            raise ReviewIntegrityError("Product seller profile is unavailable")

        db_review = Review(
            buyer_id=buyer_id,
            product_id=review.product_id,
            order_item_id=order_item.id,
            rating=review.rating,
            comment=review.comment,
            is_verified_purchase=True,
        )
        db.add(db_review)
        db.flush()
        _recalculate_seller_rating(db, seller_profile, product.seller_id)
        db.commit()
        db.refresh(db_review)
        return db_review
    except ReviewIntegrityError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(constraint_name, "constraint_name", "")
        if constraint_name in {
            "uq_reviews_verified_buyer_product",
            "uq_reviews_order_item",
        }:
            raise DuplicateReviewError("You have already reviewed this product") from exc
        raise
    except Exception:
        db.rollback()
        raise
