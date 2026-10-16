from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Dict, List, Set
from uuid import UUID

from app.api.deps import get_current_active_user, get_db
from app.models.message import Message
from app.models.order import SellerOrder
from app.models.user import User
from app.schemas.chat import MessageCreate, MessageResponse
from app.services.auth_lifecycle import AuthenticationError, validate_access_token

router = APIRouter()


class WebSocketAuthenticationError(ValueError):
    pass


def get_websocket_bearer_token(websocket: WebSocket) -> str:
    """Read a browser-compatible bearer token from WebSocket subprotocols."""
    protocols = websocket.scope.get("subprotocols", [])
    if len(protocols) == 2 and protocols[0].lower() == "bearer" and protocols[1]:
        return protocols[1]
    raise WebSocketAuthenticationError("Authentication required")


def authenticate_websocket_user(token: str, db: Session) -> User:
    """Resolve an active user from an access token before accepting the socket."""
    try:
        return validate_access_token(db, token).user
    except AuthenticationError as exc:
        raise WebSocketAuthenticationError("Invalid or expired token") from exc


def authorize_order_conversation(
    db: Session,
    seller_order_id: UUID,
    sender_id: UUID,
    receiver_id: UUID,
) -> SellerOrder:
    """Allow chat only between the buyer and seller of the referenced order."""
    seller_order = db.get(SellerOrder, seller_order_id)
    if seller_order is None or seller_order.checkout_order is None:
        raise PermissionError("Order conversation not found")

    participants = {seller_order.seller_id, seller_order.checkout_order.buyer_id}
    if sender_id == receiver_id or {sender_id, receiver_id} != participants:
        raise PermissionError("Not authorized for this order conversation")
    return seller_order


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID):
        await websocket.accept(subprotocol="bearer")
        self.active_connections.setdefault(str(user_id), set()).add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: UUID):
        connections = self.active_connections.get(str(user_id))
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            del self.active_connections[str(user_id)]

    async def send_personal_message(self, message: dict, user_id: UUID):
        for connection in tuple(self.active_connections.get(str(user_id), set())):
            await connection.send_json(message)

manager = ConnectionManager()


@router.websocket("/ws/chat/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        token = get_websocket_bearer_token(websocket)
        current_user = authenticate_websocket_user(token, db)
        if current_user.id != user_id:
            raise WebSocketAuthenticationError("Socket identity does not match token")
    except WebSocketAuthenticationError as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    await manager.connect(websocket, current_user.id)
    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                incoming = MessageCreate.model_validate_json(raw_message)
                authorize_order_conversation(
                    db,
                    seller_order_id=incoming.seller_order_id,
                    sender_id=current_user.id,
                    receiver_id=incoming.receiver_id,
                )
            except ValidationError:
                await websocket.send_json({"type": "error", "code": "invalid_message"})
                continue
            except PermissionError:
                await websocket.send_json({"type": "error", "code": "conversation_forbidden"})
                continue

            db_message = Message(
                sender_id=current_user.id,
                receiver_id=incoming.receiver_id,
                seller_order_id=incoming.seller_order_id,
                content=incoming.content,
            )
            try:
                db.add(db_message)
                db.commit()
                db.refresh(db_message)
            except SQLAlchemyError:
                db.rollback()
                await websocket.send_json({"type": "error", "code": "message_not_saved"})
                continue

            event = {
                "type": "message",
                "message": MessageResponse.model_validate(db_message).model_dump(
                    mode="json",
                    by_alias=True,
                ),
            }
            await websocket.send_json(event)
            await manager.send_personal_message(event, incoming.receiver_id)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, current_user.id)

@router.get("/history/{contact_id}", response_model=List[MessageResponse])
def get_chat_history(contact_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_active_user)):
    messages = db.query(Message).filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
        ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    
    return messages
