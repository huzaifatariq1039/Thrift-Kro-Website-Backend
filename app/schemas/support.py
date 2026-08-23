from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.support import TicketTypeEnum, TicketStatusEnum


class TicketCreate(BaseModel):
    type: TicketTypeEnum
    subject: str
    description: str
    seller_order_id: Optional[UUID] = None


class TicketUpdate(BaseModel):
    status: TicketStatusEnum
    resolution_notes: Optional[str] = None


class TicketResponse(BaseModel):
    id: UUID
    user_id: UUID
    seller_order_id: Optional[UUID] = None
    type: TicketTypeEnum
    subject: str
    description: str
    status: TicketStatusEnum
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
