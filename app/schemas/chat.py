from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    receiver_id: UUID
    seller_order_id: UUID | None
    content: str
    created_at: datetime = Field(serialization_alias="timestamp")
    is_read: bool
