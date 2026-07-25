from sqlalchemy.orm import Session
from app.models.review import Review
from app.models.order import Order, OrderStatusEnum
from app.models.user import User, SellerProfile
from app.models.product import Product
from app.schemas.review import ReviewCreate
from uuid import UUID

def create_review(db: Session, review: ReviewCreate, buyer_id: UUID, hex_code: str):
    # Verify purchase via shopping history (checking if the user has a completed/delivered order for this product)
    is_verified = False
    
    # We conceptually verify using their id and checking if an order exists.
    past_order = db.query(Order).filter(
        Order.buyer_id == buyer_id,
        Order.product_id == review.product_id,
        Order.status.in_([OrderStatusEnum.DELIVERED, OrderStatusEnum.COMPLETED_PAYOUT])
    ).first()
    
    if past_order:
        is_verified = True
        
    db_review = Review(
        buyer_id=buyer_id,
        product_id=review.product_id,
        rating=review.rating,
        comment=review.comment,
        is_verified_purchase=is_verified
    )
    db.add(db_review)
    
    # Update Seller Rating
    product = db.query(Product).filter(Product.id == review.product_id).first()
    if product:
        seller_profile = db.query(SellerProfile).filter(SellerProfile.user_id == product.seller_id).first()
        if seller_profile:
            total_score = (seller_profile.rating * seller_profile.review_count) + review.rating
            seller_profile.review_count += 1
            seller_profile.rating = total_score / seller_profile.review_count
            db.add(seller_profile)
            
    db.commit()
    db.refresh(db_review)
    return db_review

def get_reviews_by_product(db: Session, product_id: UUID):
    return db.query(Review).filter(Review.product_id == product_id).all()
