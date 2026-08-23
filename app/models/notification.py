import uuid
import enum
from sqlalchemy import Column, String, ForeignKey, DateTime, Enum, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class NotificationTypeEnum(str, enum.Enum):
    ORDER_UPDATE = "ORDER_UPDATE"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    SYSTEM_ALERT = "SYSTEM_ALERT"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(NotificationTypeEnum), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
