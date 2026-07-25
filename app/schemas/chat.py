from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class MessageCreate(BaseModel):
    receiver_id: UUID
    content: str

class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    content: str
    timestamp: datetime
    is_read: bool

    class Config:
        from_attributes = True
