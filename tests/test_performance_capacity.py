import os
import unittest
from uuid import uuid4

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers.chat import ConnectionManager
from app.core.runtime_capacity import (
    RuntimeCapacityError,
    assert_local_chat_topology,
    load_runtime_capacity,
)


class RuntimeCapacityTests(unittest.TestCase):
    def test_default_pool_stays_within_declared_budget(self):
        capacity = load_runtime_capacity({})

        self.assertEqual(capacity.database_pool_size, 5)
        self.assertEqual(capacity.database_max_overflow, 5)
        self.assertEqual(capacity.maximum_app_connections, 10)

    def test_rejects_pool_demand_over_database_budget(self):
        with self.assertRaisesRegex(RuntimeCapacityError, "exceeding"):
            load_runtime_capacity(
                {
                    "DATABASE_POOL_SIZE": "8",
                    "DATABASE_MAX_OVERFLOW": "4",
                    "DATABASE_CONNECTION_BUDGET": "10",
                }
            )

    def test_rejects_invalid_numeric_configuration(self):
        with self.assertRaisesRegex(RuntimeCapacityError, "must be an integer"):
            load_runtime_capacity({"DATABASE_POOL_SIZE": "many"})

    def test_process_local_chat_rejects_multiple_processes(self):
        capacity = load_runtime_capacity(
            {
                "WEB_CONCURRENCY": "2",
                "DATABASE_CONNECTION_BUDGET": "20",
            }
        )

        with self.assertRaisesRegex(RuntimeCapacityError, "process-local"):
            assert_local_chat_topology(capacity)


class _Socket:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.accepted = False
        self.messages = []

    async def accept(self, **_kwargs):
        self.accepted = True

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("socket closed")
        self.messages.append(message)


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivers_to_multiple_sockets_and_removes_failed_connection(self):
        manager = ConnectionManager()
        user_id = uuid4()
        healthy = _Socket()
        failed = _Socket(fail=True)
        await manager.connect(healthy, user_id)
        await manager.connect(failed, user_id)

        event = {"type": "message", "message": {"content": "hello"}}
        await manager.send_personal_message(event, user_id)

        self.assertEqual(healthy.messages, [event])
        self.assertEqual(manager.active_connections[str(user_id)], {healthy})


if __name__ == "__main__":
    unittest.main()
