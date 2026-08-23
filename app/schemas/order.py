from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.order import PaymentMethodEnum, OrderStatusEnum

class OrderItemSchema(BaseModel):
    id: UUID
    product_id: UUID
    quantity: int
    price_at_purchase: float

    class Config:
        from_attributes = True

class SellerOrderSchema(BaseModel):
    id: UUID
    seller_id: UUID
    subtotal: float
    shipping_fee: float
    platform_fee: float
    status: OrderStatusEnum
    items: List[OrderItemSchema] = []

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    shipping_address_id: UUID
    payment_method: PaymentMethodEnum

class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    shipping_address_id: UUID
    total_amount: float
    payment_method: PaymentMethodEnum
    status: OrderStatusEnum
    seller_orders: List[SellerOrderSchema] = []

    class Config:
        from_attributes = True
