import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Enum, ARRAY, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.user import VerificationStatusEnum, BusinessTypeEnum


class SellerVerificationRequest(Base):
    """
    Stores each verification submission from a seller.
    
    Rate-limit: max 3 submissions per day. After 3 rejections in a day,
    the seller enters a 1-week freeze before they can re-apply.
    """
    __tablename__ = "seller_verification_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_profile_id = Column(UUID(as_uuid=True), ForeignKey("seller_profiles.id"), nullable=False, index=True)
    
    # Business information snapshot
    business_name = Column(String, nullable=False)
    business_type = Column(Enum(BusinessTypeEnum), nullable=False)
    phone_number = Column(String, nullable=False)
    address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    cnic_number = Column(String, nullable=True)
    
    # Proof document URLs (uploaded by frontend to cloud storage)
    cnic_front_url = Column(String, nullable=False)
    cnic_back_url = Column(String, nullable=False)
    shop_photo_urls = Column(ARRAY(String), default=[])
    products_proof = Column(JSONB, default=[])
    ai_verified = Column(Boolean, default=False)
    business_reg_url = Column(String, nullable=True)
    
    # Review
    status = Column(Enum(VerificationStatusEnum), default=VerificationStatusEnum.PENDING, nullable=False)
    rejection_reason = Column(String, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    seller_profile = relationship("SellerProfile", back_populates="verification_requests")
