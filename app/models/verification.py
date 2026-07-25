import uuid
from sqlalchemy import Column, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class VerificationLog(Base):
    """Audit trail for every verification attempt (successful or not)."""
    __tablename__ = "verification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    similarity_score = Column(Float, nullable=True)
    detected_category = Column(String, nullable=True)
    liveness_passed = Column(Boolean, default=False)
    verification_hash = Column(String, unique=True, nullable=False)
    is_successful = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="verification_logs")
