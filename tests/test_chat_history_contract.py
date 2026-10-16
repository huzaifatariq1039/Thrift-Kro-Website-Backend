import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.deps import get_current_active_user, get_db
from app.api.v1.routers.chat import router as chat_router
from app.models.message import Message
from app.schemas.chat import MessageResponse


class FakeHistoryQuery:
    def __init__(self, messages):
        self.messages = messages
        self.filters = []
        self.ordering = ()
        self.offset_value = None
        self.limit_value = None

    def filter(self, *clauses):
        self.filters.extend(clauses)
        return self

    def order_by(self, *ordering):
        self.ordering = ordering
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return self.messages


class FakeHistorySession:
    def __init__(self, messages):
        self.history_query = FakeHistoryQuery(messages)

    def query(self, model):
        if model is not Message:
            raise AssertionError(f"Unexpected model queried: {model}")
        return self.history_query


class ChatHistoryContractTests(unittest.TestCase):
    def setUp(self):
        self.current_user_id = uuid4()
        self.contact_id = uuid4()
        self.created_at = datetime(2026, 10, 16, 9, 30, tzinfo=timezone.utc)
        self.message = SimpleNamespace(
            id=uuid4(),
            sender_id=self.current_user_id,
            receiver_id=self.contact_id,
            seller_order_id=None,
            content="History remains ordered and serializable",
            created_at=self.created_at,
            is_read=False,
        )
        self.db = FakeHistorySession([self.message])
        self.app = FastAPI()
        self.app.include_router(chat_router, prefix="/chat")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
            id=self.current_user_id,
            is_active=True,
        )
        self.client = TestClient(self.app)

    def test_history_orders_by_persisted_created_at_and_returns_timestamp(self):
        response = self.client.get(f"/chat/history/{self.contact_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.db.history_query.filters), 1)
        self.assertEqual(
            tuple(map(str, self.db.history_query.ordering)),
            ("messages.created_at ASC", "messages.id ASC"),
        )
        self.assertEqual(self.db.history_query.offset_value, 0)
        self.assertEqual(self.db.history_query.limit_value, 50)
        self.assertEqual(response.json()[0]["timestamp"], "2026-10-16T09:30:00Z")
        self.assertNotIn("created_at", response.json()[0])

    def test_message_dto_uses_created_at_internally_and_timestamp_on_the_wire(self):
        dto = MessageResponse.model_validate(self.message)

        self.assertEqual(dto.created_at, self.created_at)
        payload = dto.model_dump(mode="json", by_alias=True)
        self.assertEqual(payload["timestamp"], "2026-10-16T09:30:00Z")
        self.assertNotIn("created_at", payload)


if __name__ == "__main__":
    unittest.main()
