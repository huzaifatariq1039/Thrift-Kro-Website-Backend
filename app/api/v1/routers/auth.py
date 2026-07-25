from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.core.database import SessionLocal
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.schemas.user import UserCreate, UserResponse, Token, GoogleAuthRequest
import app.crud.user as crud_user
from app.api.deps import get_db

router = APIRouter()

@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud_user.create_user(db=db, user=user)

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud_user.get_user_by_email(db, email=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Guard: reject Google-only accounts that have no password set
    if user.auth_provider == "google" and not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google sign-in. Please use the Google login button.",
        )
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", response_model=Token)
def google_auth(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Authenticate or register a user via Google ID token.
    
    Flow:
    1. Verify the Google ID token.
    2. If a user with this google_id exists → log them in.
    3. If a user with this email exists → link Google account + log in.
    4. Otherwise → create a new Google user → log in.
    """
    # Verify Google ID token
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID environment variable.",
        )
    
    try:
        idinfo = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token.",
        )
    
    # Extract user info from the verified token
    google_id = idinfo["sub"]
    email = idinfo.get("email")
    full_name = idinfo.get("name", "")
    avatar_url = idinfo.get("picture")
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not have an email address.",
        )
    
    # 1. Check if user with this google_id already exists → login
    user = crud_user.get_user_by_google_id(db, google_id=google_id)
    
    if not user:
        # 2. Check if user with this email exists → link Google account
        user = crud_user.get_user_by_email(db, email=email)
        if user:
            crud_user.link_google_account(db, user=user, google_id=google_id)
        else:
            # 3. Create new user with Google auth
            user = crud_user.create_google_user(
                db,
                email=email,
                full_name=full_name,
                google_id=google_id,
                avatar_url=avatar_url,
                role=body.role,
            )
    
    # Issue our JWT
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
