"""Index product text search fields used by catalog queries.

Revision ID: 20261016_14
Revises: 20261016_13
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_14"
down_revision: Union[str, Sequence[str], None] = "20261016_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NAME_INDEX = "idx_products_name_trgm"
DESCRIPTION_INDEX = "idx_products_description_trgm"
BRAND_INDEX = "idx_products_brand_trgm"


def _indexes() -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("products")
    }


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    indexes = _indexes()
    if NAME_INDEX not in indexes:
        op.create_index(
            NAME_INDEX,
            "products",
            ["name"],
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        )
    if DESCRIPTION_INDEX not in indexes:
        op.create_index(
            DESCRIPTION_INDEX,
            "products",
            ["description"],
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        )
    if BRAND_INDEX not in indexes:
        op.create_index(
            BRAND_INDEX,
            "products",
            ["brand"],
            postgresql_using="gin",
            postgresql_ops={"brand": "gin_trgm_ops"},
        )


def downgrade() -> None:
    indexes = _indexes()
    if BRAND_INDEX in indexes:
        op.drop_index(BRAND_INDEX, table_name="products")
    if DESCRIPTION_INDEX in indexes:
        op.drop_index(DESCRIPTION_INDEX, table_name="products")
