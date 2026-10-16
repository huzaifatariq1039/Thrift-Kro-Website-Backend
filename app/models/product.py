import uuid
import enum
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text as sa_text
from app.core.database import Base
from app.core.money import MONEY_PRECISION, MONEY_SCALE, ZERO_MONEY

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

    parent = relationship("Category", remote_side=[id], back_populates="subcategories")
    subcategories = relationship("Category", back_populates="parent")
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0.0", name="products_base_price_check"),
        CheckConstraint(
            "original_price IS NULL OR original_price >= 0.0",
            name="products_original_price_check",
        ),
        Index("idx_products_catalog", "category_id", "status"),
        Index("idx_products_seller", "seller_id"),
        Index(
            "idx_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "idx_products_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        Index(
            "idx_products_brand_trgm",
            "brand",
            postgresql_using="gin",
            postgresql_ops={"brand": "gin_trgm_ops"},
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    brand = Column(String, nullable=True)
    condition = Column(
        Enum(
            ConditionEnum,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=ConditionEnum.NEW,
        nullable=False,
    )
    price = Column(Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False)
    original_price = Column(Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=True)
    status = Column(Enum(ProductStatusEnum), default=ProductStatusEnum.AVAILABLE, nullable=False)
    is_ai_verified = Column(Boolean, default=False)
    verification_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    seller = relationship("User", back_populates="products")
    category = relationship("Category", back_populates="products")
    variants = relationship(
        "ProductVariant",
        primaryjoin="and_(Product.id == ProductVariant.product_id, ProductVariant.is_active.is_(True))",
        back_populates="product",
        cascade="save-update, merge",
    )
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    tags = relationship("ProductTag", back_populates="product", cascade="all, delete-orphan")
    verification_logs = relationship("VerificationLog", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(
            "price_adjustment BETWEEN -10000000.00 AND 10000000.00",
            name="product_variants_price_adjustment_range_check",
        ),
        CheckConstraint(
            "quantity_in_stock >= 0",
            name="product_variants_quantity_in_stock_check",
        ),
        Index("idx_product_variants_product_active", "product_id", "is_active"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String, unique=True, nullable=True)
    attributes = Column(JSONB, nullable=False, server_default='{}')
    price_adjustment = Column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        default=ZERO_MONEY,
        server_default="0.00",
        nullable=False,
    )
    quantity_in_stock = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product", back_populates="variants")
    
class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        Index(
            "uq_product_images_primary_per_product",
            "product_id",
            unique=True,
            postgresql_where=sa_text("is_primary IS TRUE"),
        ),
        Index("idx_product_images_product_display", "product_id", "display_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String, nullable=False)
    is_primary = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    product = relationship("Product", back_populates="images")

class ProductTag(Base):
    __tablename__ = "product_tags"
    __table_args__ = (
        Index("idx_product_tags_product", "product_id"),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    tag_name = Column(String, nullable=False)
    
    product = relationship("Product", back_populates="tags")
