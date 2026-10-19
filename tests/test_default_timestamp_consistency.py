import ast
import os
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

import app.models  # noqa: F401
from app.core.database import Base
from app.models.seller_verification import SellerVerificationRequest
from app.schemas.chat import MessageResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DefaultAndTimestampConsistencyTests(unittest.TestCase):
    def test_pydantic_schemas_do_not_use_literal_mutable_defaults(self):
        violations = []
        for path in sorted((PROJECT_ROOT / "app" / "schemas").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign) and isinstance(
                    node.value,
                    (ast.List, ast.Dict, ast.Set),
                ):
                    violations.append(f"{path.name}:{node.lineno}")

        self.assertEqual(violations, [])

    def test_json_list_columns_use_callable_defaults(self):
        for column_name in ("shop_photo_urls", "products_proof"):
            with self.subTest(column=column_name):
                column = SellerVerificationRequest.__table__.c[column_name]
                self.assertTrue(callable(column.default.arg))
                first_default = column.default.arg(None)
                second_default = column.default.arg(None)
                self.assertEqual(first_default, [])
                self.assertEqual(second_default, [])
                self.assertIsNot(first_default, second_default)
                self.assertFalse(column.nullable)
                self.assertIsNotNone(column.server_default)

    def test_every_updated_at_column_has_a_creation_default(self):
        for table in Base.metadata.sorted_tables:
            if "updated_at" not in table.c:
                continue
            with self.subTest(table=table.name):
                column = table.c.updated_at
                self.assertFalse(column.nullable)
                self.assertIsNotNone(column.server_default)

    def test_timestamp_is_only_a_legacy_wire_alias(self):
        timestamp_columns = [
            f"{table.name}.{column.name}"
            for table in Base.metadata.sorted_tables
            for column in table.c
            if column.name == "timestamp"
        ]

        self.assertEqual(timestamp_columns, [])
        self.assertEqual(
            MessageResponse.model_fields["created_at"].serialization_alias,
            "timestamp",
        )


if __name__ == "__main__":
    unittest.main()
