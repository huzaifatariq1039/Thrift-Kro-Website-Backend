from pydantic import BaseModel
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

class ProductCreate(ProductBase):
    image_url: str
    images: List[str] = []  # Additional listing photos for AI verification
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

class ProductResponse(ProductBase):
    id: UUID
    seller_id: UUID
    image_url: str
    images: List[str] = []
    condition_score: Optional[int]
    is_ai_verified: bool
    verification_hash: Optional[str] = None
    verified_at: Optional[datetime] = None
    status: StatusEnum

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

