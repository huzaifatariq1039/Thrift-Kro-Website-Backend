from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.user import User, RoleEnum, VerificationStatusEnum
import app.crud.user as crud_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = crud_user.get_user(db, user_id=user_id)
    if user is None:
        raise credentials_exception
    return user

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

def get_current_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Only ADMIN users can access admin endpoints."""
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user
