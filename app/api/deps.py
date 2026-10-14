from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User, RoleEnum, VerificationStatusEnum
from app.services.auth_lifecycle import (
    AuthContext,
    AuthenticationError,
    validate_access_token,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_auth_context(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> AuthContext:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        return validate_access_token(db, token)
    except AuthenticationError as exc:
        raise credentials_exception from exc


def get_current_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> User:
    return context.user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_current_seller(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != RoleEnum.SELLER:
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    return current_user


def get_current_verified_seller(current_user: User = Depends(get_current_seller)) -> User:
    """Only sellers with APPROVED verification can create/manage listings."""
    if (
        not current_user.seller_profile
        or current_user.seller_profile.verification_status != VerificationStatusEnum.APPROVED
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your seller account must be verified before you can list products. "
                   "Please submit your verification documents at /sellers/verify.",
        )
    return current_user


def get_current_buyer(current_user: User = Depends(get_current_active_user)) -> User:
    """Only BUYER users can access buyer-specific endpoints like checkout."""
    if current_user.role != RoleEnum.BUYER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Buyer access required.",
        )
    return current_user


def get_current_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Only ADMIN users can access admin endpoints."""
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user
