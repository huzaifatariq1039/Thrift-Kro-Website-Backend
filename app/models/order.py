import uuid
import enum
from sqlalchemy import CheckConstraint, Column, String, Float, ForeignKey, Enum, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    COMPLETED = "COMPLETED"
    COMPLETED_PAYOUT = "COMPLETED_PAYOUT"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"

class PaymentStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    HELD = "HELD"
    SETTLED = "SETTLED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"

class CheckoutOrder(Base):
    __tablename__ = "checkout_orders"
    __table_args__ = (
        UniqueConstraint(
            "buyer_id",
            "idempotency_key",
            name="uq_checkout_orders_buyer_idempotency_key",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="PKR", server_default="PKR")
    payment_method = Column(Enum(PaymentMethodEnum), nullable=False)
    shipping_address_id = Column(UUID(as_uuid=True), ForeignKey("user_addresses.id", ondelete="SET NULL"), nullable=True)
    billing_address_id = Column(UUID(as_uuid=True), ForeignKey("user_addresses.id", ondelete="SET NULL"), nullable=True)
    shipping_address_snapshot = Column(JSONB, nullable=True)
    billing_address_snapshot = Column(JSONB, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
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
    currency = Column(String(3), nullable=False, default="PKR", server_default="PKR")
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
    payment = relationship("OrderPayment", back_populates="seller_order", uselist=False, cascade="all, delete-orphan")

    @property
    def shipping_address_snapshot(self):
        """Expose the parent order's immutable fulfillment address to serializers."""
        if self.checkout_order is None:
            return None
        return self.checkout_order.shipping_address_snapshot

class OrderPayment(Base):
    __tablename__ = "order_payments"
    __table_args__ = (
        CheckConstraint("amount >= 0.0", name="order_payments_amount_check"),
        CheckConstraint("platform_fee >= 0.0", name="order_payments_platform_fee_check"),
        CheckConstraint("seller_amount >= 0.0", name="order_payments_seller_amount_check"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("seller_orders.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    payment_method = Column(Enum(PaymentMethodEnum), nullable=False)
    status = Column(Enum(PaymentStatusEnum), nullable=False)
    amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    seller_amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="PKR")
    provider_reference = Column(String, nullable=True, unique=True)
    recorded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    seller_order = relationship("SellerOrder", back_populates="payment")
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_order_id = Column(UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), nullable=False)
    product_variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False)
    product_id_snapshot = Column(UUID(as_uuid=True), nullable=False)
    product_name_snapshot = Column(String, nullable=False)
    product_image_snapshot = Column(String, nullable=True)
    sku_snapshot = Column(String, nullable=True)
    variant_attributes_snapshot = Column(JSONB, nullable=False, default=dict, server_default="{}")
    price_at_purchase = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="PKR", server_default="PKR")
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
