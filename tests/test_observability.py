import io
import json
import logging
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.health import router as health_router
from app.core.observability import (
    ObservabilityMiddleware,
    _JsonRequestFormatter,
    current_request_id,
    request_logger,
    request_metrics,
)
from app.services.audit import record_audit_event
from app.services.auth_lifecycle import record_security_event


class _CollectingSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(ObservabilityMiddleware)

        @app.get("/items/{item_id}")
        def item(item_id: str):
            return {"item_id": item_id, "request_id": current_request_id()}

        @app.post("/security-event")
        def security_event():
            db = _CollectingSession()
            record_security_event(db, "test_login", False)
            return {"request_id": db.added[0].request_id}

        app.include_router(health_router)
        self.client = TestClient(app)

    def test_request_id_is_validated_propagated_and_logged_without_request_data(self):
        supplied = str(uuid.uuid4())
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_JsonRequestFormatter())
        request_logger.addHandler(handler)
        try:
            response = self.client.get(
                "/items/customer-secret?access_token=never-log-this",
                headers={"X-Request-ID": supplied},
            )
        finally:
            request_logger.removeHandler(handler)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], supplied)
        self.assertEqual(response.json()["request_id"], supplied)
        log_record = json.loads(stream.getvalue().strip())
        self.assertEqual(log_record["route"], "/items/{item_id}")
        self.assertNotIn("customer-secret", stream.getvalue())
        self.assertNotIn("never-log-this", stream.getvalue())

    def test_invalid_request_id_is_replaced_and_security_event_is_correlated(self):
        response = self.client.post(
            "/security-event",
            headers={"X-Request-ID": "not-a-valid-request-id"},
        )
        generated = response.headers["X-Request-ID"]
        self.assertEqual(str(uuid.UUID(generated)), generated)
        self.assertEqual(response.json()["request_id"], generated)

    def test_metrics_endpoint_is_disabled_or_bearer_protected(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("METRICS_TOKEN", None)
            self.assertEqual(self.client.get("/metrics").status_code, 404)

        with patch.dict(os.environ, {"METRICS_TOKEN": "operator-only"}):
            self.assertEqual(self.client.get("/metrics").status_code, 401)
            response = self.client.get(
                "/metrics",
                headers={"Authorization": "Bearer operator-only"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("thrift_http_requests_total", response.text)
        self.assertIn("thrift_http_request_duration_seconds_bucket", response.text)
        self.assertIn("thrift_operational_events_total", response.text)
        self.assertNotIn("customer-secret", response.text)

    def test_audit_helper_rejects_sensitive_detail_keys(self):
        db = _CollectingSession()
        with self.assertRaises(ValueError):
            record_audit_event(
                db,
                actor_id=None,
                action="account.changed",
                resource_type="user",
                resource_id=None,
                details={"email_address": "private@example.test"},
            )
        self.assertEqual(db.added, [])

    def test_audit_event_is_staged_without_committing(self):
        db = _CollectingSession()
        actor_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        event = record_audit_event(
            db,
            actor_id=actor_id,
            action="order.status_changed",
            resource_type="seller_order",
            resource_id=resource_id,
            details={"to_status": "SHIPPED"},
        )
        self.assertEqual(db.added, [event])
        self.assertEqual(event.actor_id, actor_id)
        self.assertEqual(event.resource_id, resource_id)


if __name__ == "__main__":
    unittest.main()
