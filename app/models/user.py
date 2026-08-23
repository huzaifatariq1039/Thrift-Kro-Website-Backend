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

class AddressTypeEnum(str, enum.Enum):
    SHIPPING = "SHIPPING"
    BILLING = "BILLING"
    BUSINESS = "BUSINESS"

class TransactionTypeEnum(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    PAYMENT = "PAYMENT"
    ESCROW_RELEASE = "ESCROW_RELEASE"
    REFUND = "REFUND"
    PLATFORM_FEE = "PLATFORM_FEE"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    hex_code = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.BUYER, nullable=False)
    avatar_url = Column(String, nullable=True)
    auth_provider = Column(String, default="local", nullable=False)
    google_id = Column(String, unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    seller_profile = relationship("SellerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    addresses = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="seller")

class UserAddress(Base):
    __tablename__ = "user_addresses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(AddressTypeEnum), default=AddressTypeEnum.SHIPPING, nullable=False)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    street_address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state_province = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    country = Column(String, default="Pakistan", nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="addresses")

class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    shop_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    business_type = Column(Enum(BusinessTypeEnum), nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_status = Column(Enum(VerificationStatusEnum), default=VerificationStatusEnum.UNVERIFIED, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rating = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="seller_profile")
    verification_requests = relationship("SellerVerificationRequest", back_populates="seller_profile", cascade="all, delete-orphan")

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    balance = Column(Float, default=0.0)
    currency = Column(String, default="PKR")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="wallet")
    transactions = relationship("Transaction", back_populates="wallet", cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(TransactionTypeEnum), nullable=False)
    amount = Column(Float, nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    reference_type = Column(String, nullable=True)
    status = Column(String, default="COMPLETED", nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    wallet = relationship("Wallet", back_populates="transactions")
