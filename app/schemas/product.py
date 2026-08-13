from pydantic import BaseModel, model_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.product import ConditionEnum, StatusEnum

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    original_price: Optional[float] = None
    category: str
    department: str
    size: str
    brand: Optional[str] = None
    condition: ConditionEnum
    tags: List[str] = []
    image_url: str
    images: List[str] = []

class ProductCreate(ProductBase):
    condition_score: Optional[int] = None
    is_ai_verified: bool = False

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    category: Optional[str] = None
    department: Optional[str] = None
    size: Optional[str] = None
    brand: Optional[str] = None
    condition: Optional[ConditionEnum] = None
    tags: Optional[List[str]] = None
    status: Optional[StatusEnum] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None

class ProductResponse(ProductBase):
    id: UUID
    seller_id: UUID
    seller_name: Optional[str] = None
    seller_rating: float = 4.8
    condition_score: Optional[int] = None
    is_ai_verified: bool = False
    verification_hash: Optional[str] = None
    verified_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    status: StatusEnum

    @model_validator(mode="before")
    def set_seller_name(cls, data):
        if not getattr(data, "seller_name", None) and hasattr(data, "seller"):
            seller = data.seller
            if seller and hasattr(seller, "seller_profile") and seller.seller_profile:
                data.seller_name = seller.seller_profile.shop_name
            elif seller and hasattr(seller, "full_name"):
                data.seller_name = seller.full_name
        return data

    class Config:
        from_attributes = True


# --- CSV Import Schemas ---

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

