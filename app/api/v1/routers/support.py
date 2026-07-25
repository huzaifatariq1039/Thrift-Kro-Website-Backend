"""
Support Tickets Router (For Buyers and Sellers).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.models.user import User
from app.schemas.support import TicketCreate, TicketResponse
from app.api.deps import get_db, get_current_active_user
import app.crud.support as crud_support

router = APIRouter()


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Submit a new support ticket (complaint, suggestion, query).
    """
    return crud_support.create_ticket(db, current_user.id, ticket)


@router.get("/tickets/me", response_model=List[TicketResponse])
def get_my_tickets(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all support tickets created by the current user.
    """
    return crud_support.get_user_tickets(db, current_user.id, skip, limit)
