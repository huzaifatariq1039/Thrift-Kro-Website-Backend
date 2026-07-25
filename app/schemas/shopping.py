from pydantic import BaseModel
from typing import List
from uuid import UUID
from datetime import datetime
from app.schemas.product import ProductResponse


class CartItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    product: ProductResponse
    added_at: datetime

    class Config:
        from_attributes = True


class CartSummary(BaseModel):
    items: List[CartItemResponse]
    total_price: float
    total_items: int


class WishlistItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    product: ProductResponse
    added_at: datetime

    class Config:
        from_attributes = True


class WishlistSummary(BaseModel):
    items: List[WishlistItemResponse]
    total_items: int


class CartCheckoutRequest(BaseModel):
    shipping_address: str | None = "Default User Address"

