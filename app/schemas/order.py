from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.models.order import PaymentMethodEnum, OrderStatusEnum

class OrderCreate(BaseModel):
    product_id: UUID
    shipping_address: str
    payment_method: PaymentMethodEnum

class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    seller_id: UUID
    product_id: UUID
    shipping_address: str
    subtotal: float
    escrow_fee: float
    shipping_fee: float
    total_amount: float
    payment_method: PaymentMethodEnum
    status: OrderStatusEnum

    class Config:
        from_attributes = True
