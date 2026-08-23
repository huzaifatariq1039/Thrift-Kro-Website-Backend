"""
Admin Super-Dashboard Router.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.models.user import User
from app.schemas.admin import AdminStatsResponse
from app.schemas.support import TicketResponse, TicketUpdate
from app.schemas.order import OrderResponse
from app.api.deps import get_db, get_current_admin
import app.crud.admin as crud_admin
import app.crud.support as crud_support
from app.models.order import CheckoutOrder, SellerOrder

router = APIRouter()


@router.get("/stats", response_model=AdminStatsResponse)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin)
):
    """
    Get comprehensive platform statistics: Users, Products, Orders, and Revenue.
    Only accessible by ADMIN.
    """
    return crud_admin.get_platform_stats(db)


@router.get("/orders", response_model=List[OrderResponse])
def get_all_orders(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin)
):
    """
    Get all orders on the platform for Escrow management.
    Only accessible by ADMIN.
    """
    return db.query(CheckoutOrder).order_by(CheckoutOrder.created_at.desc()).all()


@router.get("/tickets", response_model=List[TicketResponse])
def list_all_tickets(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin)
):
    """
    List all support tickets across the platform.
    Only accessible by ADMIN.
    """
    return crud_support.get_all_tickets(db, skip, limit)


@router.put("/tickets/{ticket_id}", response_model=TicketResponse)
def update_ticket_status(
    ticket_id: UUID,
    update_data: TicketUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin)
):
    """
    Update a ticket's status and add resolution notes.
    Only accessible by ADMIN.
    """
    ticket = crud_support.update_ticket(db, ticket_id, update_data)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
