import uuid
import enum
from sqlalchemy import Column, String, Float, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class PaymentMethodEnum(str, enum.Enum):
    WALLET = "WALLET"
    CARD = "CARD"

class OrderStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    FUNDS_IN_ESCROW = "FUNDS_IN_ESCROW"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED_PAYOUT = "COMPLETED_PAYOUT"
    DISPUTED = "DISPUTED"

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    shipping_address = Column(String, nullable=False) # Simplification for String instead of JSON
    subtotal = Column(Float, nullable=False)
    escrow_fee = Column(Float, nullable=False)
    shipping_fee = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(Enum(PaymentMethodEnum), nullable=False)
    status = Column(Enum(OrderStatusEnum), default=OrderStatusEnum.PENDING, nullable=False)

    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    product = relationship("Product")
