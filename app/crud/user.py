from sqlalchemy.orm import Session
from app.models.user import User, Wallet, SellerProfile, RoleEnum
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash
import secrets

def get_user(db: Session, user_id: str):
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user: UserCreate):
    hashed_password = get_password_hash(user.password)
    hex_code = secrets.token_hex(4).upper() # Generates an 8-character hex string
    
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        hex_code=hex_code,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Create Wallet for every user
    db_wallet = Wallet(user_id=db_user.id)
    db.add(db_wallet)
    
    # Create Seller Profile if role is SELLER
    if user.role == RoleEnum.SELLER:
        db_seller = SellerProfile(user_id=db_user.id, shop_name=f"{user.full_name}'s Shop")
        db.add(db_seller)
        
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: str, user_update: UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
        
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_google_id(db: Session, google_id: str):
    return db.query(User).filter(User.google_id == google_id).first()

def create_google_user(db: Session, email: str, full_name: str, google_id: str, avatar_url: str = None, role: RoleEnum = RoleEnum.BUYER):
    hex_code = secrets.token_hex(4).upper()
    
    db_user = User(
        email=email,
        hashed_password=None,
        full_name=full_name,
        hex_code=hex_code,
        role=role,
        avatar_url=avatar_url,
        auth_provider="google",
        google_id=google_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Create Wallet for every user
    db_wallet = Wallet(user_id=db_user.id)
    db.add(db_wallet)
    
    # Create Seller Profile if role is SELLER
    if role == RoleEnum.SELLER:
        db_seller = SellerProfile(user_id=db_user.id, shop_name=f"{full_name}'s Shop")
        db.add(db_seller)
        
    db.commit()
    db.refresh(db_user)
    return db_user

def link_google_account(db: Session, user: User, google_id: str):
    user.google_id = google_id
    user.auth_provider = "google"
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

