import uuid
import enum
from sqlalchemy import Column, String, Float, ForeignKey, Integer, Enum, Text, Boolean, ARRAY, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ConditionEnum(str, enum.Enum):
    EXCELLENT = "Excellent"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"

class StatusEnum(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_CART = "IN_CART"
    SOLD = "SOLD"

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    image_url = Column(String, nullable=False)
    images = Column(ARRAY(String), default=[], nullable=True)
    category = Column(String, nullable=False)
    department = Column(String, nullable=False)
    size = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    condition = Column(Enum(ConditionEnum), nullable=False)
    condition_score = Column(Integer, nullable=True)
    is_ai_verified = Column(Boolean, default=False)
    verification_hash = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    tags = Column(ARRAY(String), default=[])
    status = Column(Enum(StatusEnum), default=StatusEnum.AVAILABLE, nullable=False)

    seller = relationship("User", back_populates="products")
    verification_logs = relationship("VerificationLog", back_populates="product", cascade="all, delete-orphan")

