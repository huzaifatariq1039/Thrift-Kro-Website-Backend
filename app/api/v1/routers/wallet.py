from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.wallet import WalletDeposit, WalletResponse
from app.models.user import User
import app.crud.wallet as crud_wallet
from app.api.deps import get_db, get_current_active_user

router = APIRouter()

@router.get("/balance", response_model=WalletResponse)
def get_balance(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    wallet = crud_wallet.get_wallet_by_user(db=db, user_id=current_user.id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet

@router.post("/deposit", response_model=WalletResponse)
def deposit(deposit_data: WalletDeposit, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    wallet = crud_wallet.deposit_funds(db=db, user_id=current_user.id, amount=deposit_data.amount)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet
