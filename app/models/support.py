import uuid
import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class TicketTypeEnum(str, enum.Enum):
    COMPLAINT = "COMPLAINT"
    SUGGESTION = "SUGGESTION"
    DISPUTE = "DISPUTE"
    OTHER_QUERY = "OTHER_QUERY"


class TicketStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("idx_support_tickets_user_created", "user_id", "created_at"),
        Index("idx_support_tickets_seller_order", "seller_order_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seller_order_id = Column(UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="SET NULL"), nullable=True)
    
    type = Column(Enum(TicketTypeEnum), nullable=False)
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TicketStatusEnum), default=TicketStatusEnum.OPEN, nullable=False)
    
    resolution_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    seller_order = relationship("SellerOrder")
