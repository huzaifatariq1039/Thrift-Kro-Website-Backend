from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from uuid import UUID
from app.models.message import Message
from app.schemas.chat import MessageResponse
from app.api.deps import get_db, get_current_active_user

router = APIRouter()

# Simple in-memory connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/chat/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, db: Session = Depends(get_db)):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # For simplicity, we assume `data` is a simple string payload like "receiver_id|message"
            # In reality, this should parse JSON.
            parts = data.split("|", 1)
            if len(parts) == 2:
                receiver_id = parts[0]
                content = parts[1]
                
                # Save to database
                db_message = Message(sender_id=user_id, receiver_id=receiver_id, content=content)
                db.add(db_message)
                db.commit()
                db.refresh(db_message)
                
                # Send to receiver if online
                await manager.send_personal_message(data, receiver_id)
    except WebSocketDisconnect:
        manager.disconnect(user_id)

@router.get("/history/{contact_id}", response_model=List[MessageResponse])
def get_chat_history(contact_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_active_user)):
    user_id = str(current_user.id)
    contact_id_str = str(contact_id)
    messages = db.query(Message).filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == contact_id_str)) |
        ((Message.sender_id == contact_id_str) & (Message.receiver_id == user_id))
    ).order_by(Message.timestamp.asc()).all()
    
    return messages
