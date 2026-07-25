import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    buyer = relationship("User", foreign_keys=[buyer_id])
    product = relationship("Product")
