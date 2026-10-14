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
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    product_variant_id: UUID
    product_id: UUID = Field(validation_alias=AliasChoices("product_id_snapshot", "product_id"))
    quantity: int
    price_at_purchase: float
    currency: str = "PKR"

    # Purchase-time snapshots; never read mutable catalog fields for history.
    product_name: str = Field(validation_alias=AliasChoices("product_name_snapshot", "product_name"))
    product_image: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("product_image_snapshot", "product_image"),
    )
    sku: Optional[str] = Field(default=None, validation_alias=AliasChoices("sku_snapshot", "sku"))
    variant_attributes: dict = Field(
        default_factory=dict,
        validation_alias=AliasChoices("variant_attributes_snapshot", "variant_attributes"),
    )


class AddressSnapshot(BaseModel):
    type: Optional[str] = None
    full_name: str
    phone_number: str
    street_address: str
    city: str
    state_province: str
    postal_code: str
    country: str


class SellerOrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    seller_id: UUID
    seller_name: Optional[str] = None
    subtotal: float
    shipping_fee: float
    platform_fee: float
    total_amount: float
    currency: str = "PKR"
    status: OrderStatusEnum
    tracking_number: Optional[str] = None
    courier_name: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    shipping_address: Optional[AddressSnapshot] = Field(
        default=None,
        validation_alias=AliasChoices("shipping_address_snapshot", "shipping_address"),
    )
    items: List[OrderItemSchema] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "order_items"),
    )


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    buyer_id: UUID
    total_amount: float
    currency: str = "PKR"
    payment_method: PaymentMethodEnum
    shipping_address_id: Optional[UUID] = None
    shipping_address: Optional[AddressSnapshot] = Field(
        default=None,
        validation_alias=AliasChoices("shipping_address_snapshot", "shipping_address"),
    )
    billing_address: Optional[AddressSnapshot] = Field(
        default=None,
        validation_alias=AliasChoices("billing_address_snapshot", "billing_address"),
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    seller_orders: List[SellerOrderSchema] = Field(default_factory=list)

    # Computed aggregate status
    overall_status: Optional[str] = None

class OrderListResponse(BaseModel):
    """Paginated list of orders."""
    orders: List[OrderResponse]
    total: int
