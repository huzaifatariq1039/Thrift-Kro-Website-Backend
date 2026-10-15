"""Add correlated, append-only operational audit events.

Revision ID: 20261015_11
Revises: 20261014_10
Create Date: 2026-10-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261015_11"
down_revision: Union[str, Sequence[str], None] = "20261014_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("auth_security_events", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_auth_security_events_request_id", "auth_security_events", ["request_id"])

    op.add_column("order_status_history", sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("order_status_history", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_order_status_history_actor_id",
        "order_status_history",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_order_status_history_actor_id", "order_status_history", ["actor_id"])
    op.create_index("ix_order_status_history_request_id", "order_status_history", ["request_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), server_default="success", nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="audit_events_outcome_check"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_actor_occurred", "audit_events", ["actor_id", "occurred_at"])
    op.create_index(
        "ix_audit_events_resource_occurred",
        "audit_events",
        ["resource_type", "resource_id", "occurred_at"],
    )
    op.create_index("ix_audit_events_action_occurred", "audit_events", ["action", "occurred_at"])

    op.execute(
        """
        CREATE FUNCTION prevent_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation()")
    op.drop_table("audit_events")

    op.drop_index("ix_order_status_history_request_id", table_name="order_status_history")
    op.drop_index("ix_order_status_history_actor_id", table_name="order_status_history")
    op.drop_constraint("fk_order_status_history_actor_id", "order_status_history", type_="foreignkey")
    op.drop_column("order_status_history", "request_id")
    op.drop_column("order_status_history", "actor_id")

    op.drop_index("ix_auth_security_events_request_id", table_name="auth_security_events")
    op.drop_column("auth_security_events", "request_id")
