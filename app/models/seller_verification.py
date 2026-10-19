import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.user import BusinessTypeEnum, VerificationStatusEnum


class SellerVerificationRequest(Base):
    __tablename__ = "seller_verification_requests"
    __table_args__ = (
        Index(
            "uq_seller_verification_one_pending",
            "seller_profile_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "idx_seller_verification_seller_created",
            "seller_profile_id",
            "created_at",
            "id",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("seller_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Business information snapshot
    business_name = Column(String, nullable=False)
    business_type = Column(Enum(BusinessTypeEnum), nullable=False)
    phone_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    cnic_number = Column(String, nullable=True)
    
    # Proof document URLs
    cnic_front_url = Column(String, nullable=False)
    cnic_back_url = Column(String, nullable=False)
    business_reg_url = Column(String, nullable=True)
    shop_photo_urls = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    products_proof = Column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    ai_verified = Column(Boolean, default=False)
    
    # Review
    status = Column(
        Enum(VerificationStatusEnum),
        default=VerificationStatusEnum.PENDING,
        nullable=False,
    )
    rejection_reason = Column(String, nullable=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    
    # Relationships
    seller_profile = relationship(
        "SellerProfile",
        back_populates="verification_requests",
    )
    reviewer = relationship("User", foreign_keys=[reviewed_by])
