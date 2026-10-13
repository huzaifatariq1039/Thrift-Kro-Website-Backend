from sqlalchemy.orm import Session
from app.models.user import Wallet
from uuid import UUID

def get_wallet_by_user(db: Session, user_id: UUID):
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()
