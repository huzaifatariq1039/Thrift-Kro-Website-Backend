from sqlalchemy.orm import Session
from app.models.user import Wallet
from uuid import UUID

def get_wallet_by_user(db: Session, user_id: UUID):
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()

def deposit_funds(db: Session, user_id: UUID, amount: float):
    wallet = get_wallet_by_user(db, user_id)
    if wallet:
        wallet.balance += amount
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet
