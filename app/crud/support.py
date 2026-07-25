from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.models.support import SupportTicket
from app.schemas.support import TicketCreate, TicketUpdate


def create_ticket(db: Session, user_id: UUID, ticket: TicketCreate) -> SupportTicket:
    db_ticket = SupportTicket(
        user_id=user_id,
        type=ticket.type,
        subject=ticket.subject,
        description=ticket.description,
        order_id=ticket.order_id
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


def get_user_tickets(db: Session, user_id: UUID, skip: int = 0, limit: int = 50) -> List[SupportTicket]:
    return db.query(SupportTicket).filter(
        SupportTicket.user_id == user_id
    ).order_by(SupportTicket.created_at.desc()).offset(skip).limit(limit).all()


def get_all_tickets(db: Session, skip: int = 0, limit: int = 100) -> List[SupportTicket]:
    return db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).offset(skip).limit(limit).all()


def get_ticket(db: Session, ticket_id: UUID) -> SupportTicket:
    return db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()


def update_ticket(db: Session, ticket_id: UUID, update_data: TicketUpdate) -> SupportTicket:
    db_ticket = get_ticket(db, ticket_id)
    if not db_ticket:
        return None
        
    db_ticket.status = update_data.status
    if update_data.resolution_notes is not None:
        db_ticket.resolution_notes = update_data.resolution_notes
        
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket
