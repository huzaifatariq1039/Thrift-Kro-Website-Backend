from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.schemas.order import OrderCreate, OrderResponse
from app.models.user import User, RoleEnum
from app.models.order import OrderStatusEnum
import app.crud.order as crud_order
from app.api.deps import get_db, get_current_active_user

router = APIRouter()

@router.post("/checkout", response_model=OrderResponse)
def checkout(order: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    db_order = crud_order.create_order(db=db, order=order, buyer_id=current_user.id)
    if db_order == "INSUFFICIENT_FUNDS":
        raise HTTPException(status_code=400, detail="Insufficient funds in wallet")
    if db_order is None:
        raise HTTPException(status_code=400, detail="Product is not available")
    return db_order

@router.get("/", response_model=List[OrderResponse])
def get_orders(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    is_seller = current_user.role == RoleEnum.SELLER
    return crud_order.get_orders_by_user(db=db, user_id=current_user.id, is_seller=is_seller)

@router.put("/{id}/status", response_model=OrderResponse)
def update_order_status(id: UUID, status: OrderStatusEnum, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    existing_order = crud_order.get_orders_by_user(db=db, user_id=current_user.id, is_seller=True)
    # Check order ownership or admin status
    db_order = db.query(crud_order.Order).filter(crud_order.Order.id == id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if current_user.role != RoleEnum.ADMIN and current_user.id not in (db_order.seller_id, db_order.buyer_id):
        raise HTTPException(status_code=403, detail="Not authorized to update this order")
        
    updated_order = crud_order.update_order_status(db=db, order_id=id, status=status)
    return updated_order

@router.post("/{id}/release-escrow", response_model=OrderResponse)
def release_escrow(id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    db_order = db.query(crud_order.Order).filter(crud_order.Order.id == id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if current_user.role != RoleEnum.ADMIN and current_user.id != db_order.buyer_id:
        raise HTTPException(status_code=403, detail="Only the buyer can release escrow funds for this order")
        
    result_order = crud_order.release_escrow(db=db, order_id=id)
    if not result_order:
        raise HTTPException(status_code=400, detail="Order is not in DELIVERED status")
    return result_order
