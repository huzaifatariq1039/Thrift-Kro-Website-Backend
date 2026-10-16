"""Shared authentication helpers for browser WebSocket endpoints."""

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth_lifecycle import AuthenticationError, validate_access_token


class WebSocketAuthenticationError(ValueError):
    pass


def get_websocket_bearer_token(websocket: WebSocket) -> str:
    """Read a bearer token from WebSocket subprotocols, never from the URL."""
    protocols = websocket.scope.get("subprotocols", [])
    if len(protocols) == 2 and protocols[0].lower() == "bearer" and protocols[1]:
        return protocols[1]
    raise WebSocketAuthenticationError("Authentication required")


def authenticate_websocket_user(token: str, db: Session) -> User:
    """Resolve an active user through the revocable HTTP session policy."""
    try:
        return validate_access_token(db, token).user
    except AuthenticationError as exc:
        raise WebSocketAuthenticationError("Invalid or expired token") from exc
