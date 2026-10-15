from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.product import ConditionEnum, ProductStatusEnum


# ─── Nested Schemas ───────────────────────────────────────────────────

class ProductImageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: str = Field(..., max_length=2048)
    is_primary: bool = False
    display_order: int = Field(0, ge=0)


class ProductImageResponse(BaseModel):
    id: UUID
    image_url: str
    is_primary: bool
    display_order: int

    class Config:
        from_attributes = True


class ProductVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: Optional[str] = Field(None, max_length=100)
    attributes: dict = Field(default_factory=dict, description="e.g. {'size': 'L', 'color': 'Blue'}")
    price_adjustment: float = 0.0
    quantity_in_stock: int = Field(1, ge=0)


class ProductVariantResponse(BaseModel):
    id: UUID
    sku: Optional[str] = None
    attributes: dict = Field(default_factory=dict)
    price_adjustment: float = 0.0
    quantity_in_stock: int = 1
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductTagCreate(BaseModel):
    tag_name: str = Field(..., max_length=100)


class ProductTagResponse(BaseModel):
    id: UUID
    tag_name: str

    class Config:
        from_attributes = True


# ─── Category Schemas ─────────────────────────────────────────────────

class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None
    is_active: bool = True

    class Config:
        from_attributes = True


# ─── Product CRUD Schemas ─────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    price: float = Field(..., gt=0, le=10_000_000)
    original_price: Optional[float] = Field(None, gt=0, le=10_000_000)
    brand: Optional[str] = Field(None, max_length=200)
    condition: ConditionEnum


class ProductCreate(ProductBase):
    model_config = ConfigDict(extra="forbid")

    category_id: Optional[UUID] = None
    images: List[ProductImageCreate] = Field(..., min_length=1)
    variants: List[ProductVariantCreate] = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list, description="List of tag strings")

    @model_validator(mode="before")
    @classmethod
    def reject_server_managed_verification_fields(cls, data):
        """Prevent listing authors from asserting product-verification results."""
        if isinstance(data, dict):
            forbidden = sorted(
                {"is_ai_verified", "condition_score", "verification_hash"}.intersection(data)
            )
            if forbidden:
                raise ValueError(
                    "Product verification fields are server-managed: "
                    + ", ".join(forbidden)
                )
        return data


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=2, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    price: Optional[float] = Field(None, gt=0, le=10_000_000)
    original_price: Optional[float] = Field(None, gt=0, le=10_000_000)
    brand: Optional[str] = Field(None, max_length=200)
    condition: Optional[ConditionEnum] = None
    category_id: Optional[UUID] = None
    status: Optional[ProductStatusEnum] = None
    images: Optional[List[ProductImageCreate]] = Field(None, min_length=1)
    variants: Optional[List[ProductVariantCreate]] = Field(None, min_length=1)
    tags: Optional[List[str]] = None


class ProductResponse(BaseModel):
    id: UUID
    seller_id: UUID
    name: str
    description: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    brand: Optional[str] = None
    condition: ConditionEnum
    status: ProductStatusEnum
    category_id: Optional[UUID] = None
    category: Optional[CategoryResponse] = None
    is_ai_verified: bool = False
    verification_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # Nested relationships
    images: List[ProductImageResponse] = Field(default_factory=list)
    variants: List[ProductVariantResponse] = Field(default_factory=list)
    tags: List[ProductTagResponse] = Field(default_factory=list)

    # Computed seller info
    seller_name: Optional[str] = None
    seller_rating: float = 0.0
    seller_shop_logo: Optional[str] = None

    @model_validator(mode="before")
    def populate_seller_info(cls, data):
        """Populate seller_name and seller_rating from the seller relationship."""
        if hasattr(data, "seller") and data.seller:
            seller = data.seller
            if not getattr(data, "seller_name", None):
                if hasattr(seller, "seller_profile") and seller.seller_profile:
                    data.seller_name = seller.seller_profile.shop_name
                    data.seller_rating = seller.seller_profile.rating or 0.0
                    data.seller_shop_logo = seller.seller_profile.logo_url
                elif hasattr(seller, "full_name"):
                    data.seller_name = seller.full_name
        return data

    class Config:
        from_attributes = True


# ─── CSV Import Schemas ───────────────────────────────────────────────

class CSVImportRowResult(BaseModel):
    """Result for a single row in the CSV import."""
    row_number: int
    success: bool
    product_name: Optional[str] = None
    product_id: Optional[UUID] = None
    error: Optional[str] = None


class CSVImportResponse(BaseModel):
    """Overall result of a CSV bulk import."""
    total_rows: int
    successful: int
    failed: int
    results: List[CSVImportRowResult]
