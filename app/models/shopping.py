import uuid
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class CartSession(Base):
    __tablename__ = "cart_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    items = relationship("CartItem", back_populates="cart_session", cascade="all, delete-orphan")

class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint(
            "cart_session_id",
            "product_variant_id",
            name="uq_cart_items_session_variant",
        ),
        CheckConstraint("quantity > 0", name="cart_items_quantity_check"),
        Index("idx_cart_items_session_added", "cart_session_id", "added_at"),
        Index("idx_cart_items_variant", "product_variant_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    cart_session_id = Column(UUID(as_uuid=True), ForeignKey("cart_sessions.id", ondelete="CASCADE"), nullable=False)
    product_variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    cart_session = relationship("CartSession", back_populates="items")
    product_variant = relationship("ProductVariant")

class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_wishlist_items_user_product",
        ),
        Index("idx_wishlist_items_user_added", "user_id", "added_at"),
        Index("idx_wishlist_items_product", "product_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    product = relationship("Product")
