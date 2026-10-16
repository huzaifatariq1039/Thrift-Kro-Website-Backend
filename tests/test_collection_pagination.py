import os
import unittest
from uuid import uuid4

from fastapi import FastAPI

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

import app.crud.category as crud_category
import app.crud.order as crud_order
import app.crud.review as crud_review
from app.api.v1.routers import (
    admin,
    categories,
    chat,
    orders,
    products,
    reviews,
    sellers,
    stores,
    support,
)


class RecordingQuery:
    def __init__(self):
        self.offset_value = None
        self.limit_value = None

    def options(self, *args):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return []


class RecordingSession:
    def __init__(self):
        self.queries = []

    def query(self, model):
        query = RecordingQuery()
        self.queries.append(query)
        return query


class CollectionPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        for router, prefix in (
            (admin.router, "/admin"),
            (orders.router, "/orders"),
            (reviews.router, "/reviews"),
            (chat.router, "/chat"),
            (categories.router, "/categories"),
            (products.router, "/products"),
            (sellers.router, "/sellers"),
            (support.router, "/support"),
            (stores.router, "/stores"),
        ):
            app.include_router(router, prefix=prefix)
        cls.openapi = app.openapi()

    def test_collection_routes_publish_bounded_offset_pagination(self):
        paths = (
            "/admin/orders",
            "/admin/tickets",
            "/orders/",
            "/orders/seller",
            "/reviews/product/{product_id}",
            "/chat/history/{contact_id}",
            "/categories/",
            "/products/",
            "/products/seller/me",
            "/sellers/verification/pending",
            "/support/tickets/me",
            "/stores/ranking",
        )

        for path in paths:
            with self.subTest(path=path):
                operation = self.openapi["paths"][path]["get"]
                parameters = {
                    parameter["name"]: parameter
                    for parameter in operation["parameters"]
                    if parameter["in"] == "query"
                }
                self.assertEqual(parameters["skip"]["schema"]["minimum"], 0)
                self.assertEqual(parameters["skip"]["schema"]["default"], 0)
                self.assertEqual(parameters["limit"]["schema"]["minimum"], 1)
                self.assertEqual(parameters["limit"]["schema"]["maximum"], 100)
                self.assertLessEqual(parameters["limit"]["schema"]["default"], 100)

    def test_order_queries_apply_caller_page_to_buyers_and_sellers(self):
        db = RecordingSession()

        crud_order.get_orders_by_user(db, uuid4(), is_seller=False, skip=20, limit=15)
        crud_order.get_orders_by_user(db, uuid4(), is_seller=True, skip=35, limit=10)

        self.assertEqual(
            [(query.offset_value, query.limit_value) for query in db.queries],
            [(20, 15), (35, 10)],
        )

    def test_review_and_category_queries_apply_caller_page(self):
        db = RecordingSession()

        crud_review.get_reviews_by_product(db, uuid4(), skip=5, limit=25)
        crud_category.get_categories(db, skip=10, limit=20)
        crud_category.get_all_categories(db, skip=30, limit=40)

        self.assertEqual(
            [(query.offset_value, query.limit_value) for query in db.queries],
            [(5, 25), (10, 20), (30, 40)],
        )


if __name__ == "__main__":
    unittest.main()
