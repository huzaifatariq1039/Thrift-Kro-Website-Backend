"""
Order schemas — aligned with the multi-vendor CheckoutOrder → SellerOrder → OrderItem model.
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.order import PaymentMethodEnum, OrderStatusEnum


# ─── Request Schemas ──────────────────────────────────────────────────

class OrderCreate(BaseModel):
    """Create an order from the current cart."""
    shipping_address_id: Optional[UUID] = None
    payment_method: PaymentMethodEnum = PaymentMethodEnum.CASH_ON_DELIVERY


class OrderStatusUpdate(BaseModel):
    """Update status of a seller order."""
    status: OrderStatusEnum
    tracking_number: Optional[str] = Field(None, max_length=200)
    courier_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)


# ─── Response Schemas ─────────────────────────────────────────────────

class OrderItemSchema(BaseModel):
    id: UUID
    product_variant_id: UUID
    quantity: int
    price_at_purchase: float

    # Computed product info
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    variant_attributes: Optional[dict] = None

    class Config:
        from_attributes = True


class SellerOrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    seller_id: UUID
    seller_name: Optional[str] = None
    subtotal: float
    shipping_fee: float
    platform_fee: float
    total_amount: float
    status: OrderStatusEnum
    tracking_number: Optional[str] = None
    courier_name: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    items: List[OrderItemSchema] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "order_items"),
    )


class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    total_amount: float
    payment_method: PaymentMethodEnum
    shipping_address_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    seller_orders: List[SellerOrderSchema] = Field(default_factory=list)

    # Computed aggregate status
    overall_status: Optional[str] = None

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Paginated list of orders."""
    orders: List[OrderResponse]
    total: int
