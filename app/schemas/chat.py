from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime

class MessageCreate(BaseModel):
    seller_order_id: UUID
    receiver_id: UUID
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content must not be blank")
        return value

class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    seller_order_id: UUID | None
    content: str
    timestamp: datetime = Field(validation_alias="created_at")
    is_read: bool

    class Config:
        from_attributes = True
