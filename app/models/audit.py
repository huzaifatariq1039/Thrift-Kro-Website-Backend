"""Append-only operational audit events."""

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failure')",
            name="audit_events_outcome_check",
        ),
        Index("ix_audit_events_actor_occurred", "actor_id", "occurred_at"),
        Index("ix_audit_events_resource_occurred", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_events_action_occurred", "action", "occurred_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(96), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    outcome = Column(String(16), nullable=False, default="success", server_default="success")
    details = Column(JSONB, nullable=False, default=dict, server_default="{}")
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
