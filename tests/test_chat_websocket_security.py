import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.deps import get_db
from app.api.v1.routers.chat import manager, router as chat_router


class FakeSession:
    def __init__(self, seller_order):
        self.seller_order = seller_order
        self.added = []

    def get(self, _model, object_id):
        if object_id == self.seller_order.id:
            return self.seller_order
        return None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None

    def refresh(self, value):
        value.id = uuid4()
        value.created_at = datetime.now(timezone.utc)
        value.is_read = False

    def rollback(self):
        return None


class ChatWebSocketSecurityTests(unittest.TestCase):
    def setUp(self):
        self.buyer_id = uuid4()
        self.seller_id = uuid4()
        self.order_id = uuid4()
        self.user = SimpleNamespace(id=self.buyer_id, is_active=True)
        self.order = SimpleNamespace(
            id=self.order_id,
            seller_id=self.seller_id,
            checkout_order=SimpleNamespace(buyer_id=self.buyer_id),
        )
        self.db = FakeSession(self.order)
        self.app = FastAPI()
        self.app.include_router(chat_router, prefix="/chat")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        manager.active_connections.clear()

    def tearDown(self):
        manager.active_connections.clear()

    def test_rejects_socket_without_credentials_before_acceptance(self):
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect(f"/chat/ws/chat/{self.buyer_id}"):
                pass
        self.assertEqual(caught.exception.code, 1008)

    def test_rejects_path_identity_that_does_not_match_token(self):
        token = "session-bound-test-token"
        context = SimpleNamespace(user=self.user)
        with patch("app.api.v1.routers.chat.validate_access_token", return_value=context):
            with self.assertRaises(WebSocketDisconnect) as caught:
                with self.client.websocket_connect(
                    f"/chat/ws/chat/{uuid4()}",
                    subprotocols=["bearer", token],
                ):
                    pass
        self.assertEqual(caught.exception.code, 1008)

    def test_persists_authenticated_sender_for_authorized_order(self):
        token = "session-bound-test-token"
        context = SimpleNamespace(user=self.user)
        with patch("app.api.v1.routers.chat.validate_access_token", return_value=context):
            with self.client.websocket_connect(
                f"/chat/ws/chat/{self.buyer_id}",
                subprotocols=["bearer", token],
            ) as websocket:
                websocket.send_json(
                    {
                        "seller_order_id": str(self.order_id),
                        "receiver_id": str(self.seller_id),
                        "content": "  Is this ready to ship?  ",
                    }
                )
                event = websocket.receive_json()

        self.assertEqual(event["type"], "message")
        self.assertEqual(event["message"]["sender_id"], str(self.buyer_id))
        self.assertEqual(len(self.db.added), 1)
        self.assertEqual(self.db.added[0].sender_id, self.buyer_id)
        self.assertEqual(self.db.added[0].content, "Is this ready to ship?")

    def test_rejects_message_outside_order_participants(self):
        token = "session-bound-test-token"
        attacker_selected_receiver = uuid4()
        context = SimpleNamespace(user=self.user)
        with patch("app.api.v1.routers.chat.validate_access_token", return_value=context):
            with self.client.websocket_connect(
                f"/chat/ws/chat/{self.buyer_id}",
                subprotocols=["bearer", token],
            ) as websocket:
                websocket.send_json(
                    {
                        "seller_order_id": str(self.order_id),
                        "receiver_id": str(attacker_selected_receiver),
                        "content": "Unauthorized message",
                    }
                )
                event = websocket.receive_json()

        self.assertEqual(event, {"type": "error", "code": "conversation_forbidden"})
        self.assertEqual(self.db.added, [])


if __name__ == "__main__":
    unittest.main()
