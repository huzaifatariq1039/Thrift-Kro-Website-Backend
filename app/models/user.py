import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Float, ForeignKey, Integer, Enum, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class RoleEnum(str, enum.Enum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"

class BusinessTypeEnum(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    SHOP = "SHOP"
    WAREHOUSE = "WAREHOUSE"

class VerificationStatusEnum(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    hex_code = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.BUYER, nullable=False)
    avatar_url = Column(String, nullable=True)
    auth_provider = Column(String, default="local", nullable=False)  # "local" or "google"
    google_id = Column(String, unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    seller_profile = relationship("SellerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    products = relationship("Product", back_populates="seller")

class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    shop_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    # Business information
    phone_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    business_type = Column(Enum(BusinessTypeEnum), nullable=True)
    cnic_number = Column(String, nullable=True)
    
    # Verification
    is_verified = Column(Boolean, default=False)
    verification_status = Column(Enum(VerificationStatusEnum), default=VerificationStatusEnum.UNVERIFIED, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Ratings
    rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)

    user = relationship("User", back_populates="seller_profile")
    verification_requests = relationship("SellerVerificationRequest", back_populates="seller_profile", cascade="all, delete-orphan")

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    balance = Column(Float, default=0.0)
    currency = Column(String, default="PKR")

    user = relationship("User", back_populates="wallet")

