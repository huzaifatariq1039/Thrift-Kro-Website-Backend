import uuid
import enum
from sqlalchemy import Column, String, Float, ForeignKey, Enum, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class PaymentMethodEnum(str, enum.Enum):
    WALLET = "WALLET"
    CARD = "CARD"
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"

class OrderStatusEnum(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID_FUNDS_IN_ESCROW = "PAID_FUNDS_IN_ESCROW"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED_PAYOUT = "COMPLETED_PAYOUT"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"

class CheckoutOrder(Base):
    __tablename__ = "checkout_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(Enum(PaymentMethodEnum), nullable=False)
    shipping_address_id = Column(UUID(as_uuid=True), ForeignKey("user_addresses.id", ondelete="SET NULL"), nullable=True)
    billing_address_id = Column(UUID(as_uuid=True), ForeignKey("user_addresses.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    buyer = relationship("User", foreign_keys=[buyer_id])
    seller_orders = relationship("SellerOrder", back_populates="checkout_order", cascade="all, delete-orphan")

class SellerOrder(Base):
    __tablename__ = "seller_orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    checkout_order_id = Column(UUID(as_uuid=True), ForeignKey("checkout_orders.id", ondelete="CASCADE"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    subtotal = Column(Float, nullable=False)
    shipping_fee = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(Enum(OrderStatusEnum), default=OrderStatusEnum.PENDING_PAYMENT, nullable=False)
    tracking_number = Column(String, nullable=True)
    courier_name = Column(String, nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    checkout_order = relationship("CheckoutOrder", back_populates="seller_orders")
    seller = relationship("User", foreign_keys=[seller_id])
    order_items = relationship("OrderItem", back_populates="seller_order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="seller_order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_order_id = Column(UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), nullable=False)
    product_variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False)
    price_at_purchase = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    seller_order = relationship("SellerOrder", back_populates="order_items")
    product_variant = relationship("ProductVariant")
    reviews = relationship("Review", back_populates="order_item", cascade="all, delete-orphan")

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_order_id = Column(UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(OrderStatusEnum), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    seller_order = relationship("SellerOrder", back_populates="status_history")
