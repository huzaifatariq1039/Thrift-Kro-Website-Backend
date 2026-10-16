import uuid
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="reviews_rating_check"),
        CheckConstraint(
            "is_verified_purchase IS FALSE OR order_item_id IS NOT NULL",
            name="reviews_verified_requires_order_item",
        ),
        Index(
            "uq_reviews_verified_buyer_product",
            "buyer_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_verified_purchase IS TRUE"),
        ),
        Index(
            "uq_reviews_order_item",
            "order_item_id",
            unique=True,
            postgresql_where=text("order_item_id IS NOT NULL"),
        ),
        Index("idx_reviews_product_created", "product_id", "created_at", "id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False, server_default="false", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    buyer = relationship("User", foreign_keys=[buyer_id])
    product = relationship("Product")
    order_item = relationship("OrderItem", back_populates="reviews")
