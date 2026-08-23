from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.user import RoleEnum, VerificationStatusEnum, BusinessTypeEnum
import re

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: RoleEnum = RoleEnum.BUYER

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Password must contain at least 8 characters, one uppercase, one lowercase, one number and one special character")

    @field_validator("password")
    def validate_password(cls, v):
        if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$", v):
            raise ValueError("Password must contain at least 8 characters, one uppercase, one lowercase, one number and one special character")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuthRequest(BaseModel):
    id_token: str
    role: RoleEnum = RoleEnum.BUYER

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

class SellerProfileResponse(BaseModel):
    """Nested seller profile data returned with UserResponse."""
    id: UUID
    shop_name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    business_type: Optional[BusinessTypeEnum] = None
    is_verified: bool = False
    verification_status: VerificationStatusEnum = VerificationStatusEnum.UNVERIFIED
    verified_at: Optional[datetime] = None
    rating: float = 0.0
    review_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserResponse(UserBase):
    id: UUID
    hex_code: str
    avatar_url: Optional[str]
    auth_provider: str = "local"
    is_active: bool
    created_at: datetime
    seller_profile: Optional[SellerProfileResponse] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
