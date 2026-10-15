"""Helpers for writing privacy-safe audit events in the caller's transaction."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.observability import current_request_id, request_metrics
from app.models.audit import AuditEvent


_SENSITIVE_KEY_FRAGMENTS = {
    "address",
    "authorization",
    "cnic",
    "cookie",
    "email",
    "password",
    "phone",
    "secret",
    "token",
    "url",
}


def _assert_safe_details(value: Any, path: str = "details") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS):
                raise ValueError(f"Sensitive audit detail key is not permitted: {path}.{key}")
            _assert_safe_details(nested_value, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested_value in enumerate(value):
            _assert_safe_details(nested_value, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise TypeError(f"Unsupported audit detail value at {path}")


def record_audit_event(
    db: Session,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Stage an audit event without committing outside the business transaction."""
    safe_details = details or {}
    _assert_safe_details(safe_details)
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=current_request_id(),
        outcome=outcome,
        details=safe_details,
    )
    db.add(event)
    request_metrics.operational_event("audit", action, outcome)
    return event
