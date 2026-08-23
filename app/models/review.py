import uuid
from sqlalchemy import Column, Integer, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    buyer = relationship("User", foreign_keys=[buyer_id])
    product = relationship("Product")
    order_item = relationship("OrderItem", back_populates="reviews")
