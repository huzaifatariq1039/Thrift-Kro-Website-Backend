import uuid
import enum
from sqlalchemy import Column, String, Float, ForeignKey, Integer, Enum, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ConditionEnum(str, enum.Enum):
    NEW = "New"
    LIKE_NEW = "Like New"
    EXCELLENT = "Excellent"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"

class ProductStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    ARCHIVED = "ARCHIVED"

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subcategories = relationship("Category", backref="parent", remote_side=[id])
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    brand = Column(String, nullable=True)
    condition = Column(Enum(ConditionEnum), default=ConditionEnum.NEW, nullable=False)
    base_price = Column(Float, nullable=False)
    original_price = Column(Float, nullable=True)
    status = Column(Enum(ProductStatusEnum), default=ProductStatusEnum.AVAILABLE, nullable=False)
    is_ai_verified = Column(Boolean, default=False)
    verification_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    seller = relationship("User", back_populates="products")
    category = relationship("Category", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    tags = relationship("ProductTag", back_populates="product", cascade="all, delete-orphan")
    verification_logs = relationship("VerificationLog", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String, unique=True, nullable=True)
    attributes = Column(JSONB, nullable=False, server_default='{}')
    price_adjustment = Column(Float, default=0.0)
    quantity_in_stock = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product", back_populates="variants")
    
class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String, nullable=False)
    is_primary = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    product = relationship("Product", back_populates="images")

class ProductTag(Base):
    __tablename__ = "product_tags"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    tag_name = Column(String, nullable=False)
    
    product = relationship("Product", back_populates="tags")
