"""Track owned media assets and bind product images to their lifecycle.

Revision ID: 20261018_15
Revises: 20261016_14
Create Date: 2026-10-18
"""

from datetime import datetime, timezone
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261018_15"
down_revision: Union[str, Sequence[str], None] = "20261016_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


media_purpose = postgresql.ENUM(
    "PRODUCT_IMAGE",
    "KYC_DOCUMENT",
    name="media_purpose",
    create_type=False,
)
media_visibility = postgresql.ENUM(
    "PUBLIC",
    "PRIVATE",
    name="media_visibility",
    create_type=False,
)
media_status = postgresql.ENUM(
    "PENDING",
    "ATTACHED",
    "DELETION_PENDING",
    "DELETING",
    "DELETED",
    name="media_status",
    create_type=False,
)
media_moderation_status = postgresql.ENUM(
    "NOT_REVIEWED",
    "APPROVED",
    "REJECTED",
    name="media_moderation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    media_purpose.create(bind, checkfirst=True)
    media_visibility.create(bind, checkfirst=True)
    media_status.create(bind, checkfirst=True)
    media_moderation_status.create(bind, checkfirst=True)

    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_public_id", sa.String(length=512), nullable=False),
        sa.Column("secure_url", sa.String(length=2048), nullable=False),
        sa.Column("purpose", media_purpose, nullable=False),
        sa.Column("visibility", media_visibility, nullable=False),
        sa.Column(
            "status",
            media_status,
            nullable=False,
            server_default=sa.text("'PENDING'::media_status"),
        ),
        sa.Column(
            "moderation_status",
            media_moderation_status,
            nullable=False,
            server_default=sa.text("'NOT_REVIEWED'::media_moderation_status"),
        ),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("byte_size >= 0", name="media_assets_byte_size_check"),
        sa.CheckConstraint("width > 0", name="media_assets_width_check"),
        sa.CheckConstraint("height > 0", name="media_assets_height_check"),
        sa.CheckConstraint(
            "purpose != 'KYC_DOCUMENT' OR visibility = 'PRIVATE'",
            name="media_assets_kyc_private_check",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_media_assets_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_public_id",
            name="uq_media_assets_provider_identity",
        ),
    )
    op.create_index(
        "idx_media_assets_owner_status",
        "media_assets",
        ["owner_id", "status"],
    )
    op.create_index(
        "idx_media_assets_cleanup",
        "media_assets",
        ["status", "delete_after"],
    )

    op.add_column(
        "product_images",
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_images_media_asset_id",
        "product_images",
        "media_assets",
        ["media_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_product_images_media_asset_id",
        "product_images",
        ["media_asset_id"],
    )

    legacy_images = bind.execute(
        sa.text(
            """
            SELECT pi.id, pi.image_url, pi.created_at, p.seller_id
            FROM product_images AS pi
            JOIN products AS p ON p.id = pi.product_id
            WHERE pi.media_asset_id IS NULL
            """
        )
    ).mappings()
    for image in legacy_images:
        asset_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO media_assets (
                    id, owner_id, provider, provider_public_id, secure_url,
                    purpose, visibility, status, moderation_status,
                    content_type, byte_size, width, height,
                    attached_at, created_at, updated_at
                ) VALUES (
                    :id, :owner_id, 'legacy', :provider_public_id, :secure_url,
                    'PRODUCT_IMAGE', 'PUBLIC', 'ATTACHED', 'NOT_REVIEWED',
                    'image/unknown', 0, 1, 1,
                    :created_at, :created_at, now()
                )
                """
            ),
            {
                "id": asset_id,
                "owner_id": image["seller_id"],
                "provider_public_id": f"legacy/product-image/{image['id']}",
                "secure_url": image["image_url"],
                "created_at": image["created_at"] or datetime.now(timezone.utc),
            },
        )
        bind.execute(
            sa.text(
                "UPDATE product_images SET media_asset_id = :asset_id WHERE id = :image_id"
            ),
            {"asset_id": asset_id, "image_id": image["id"]},
        )

    op.alter_column("product_images", "media_asset_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint(
        "uq_product_images_media_asset_id",
        "product_images",
        type_="unique",
    )
    op.drop_constraint(
        "fk_product_images_media_asset_id",
        "product_images",
        type_="foreignkey",
    )
    op.drop_column("product_images", "media_asset_id")
    op.drop_index("idx_media_assets_cleanup", table_name="media_assets")
    op.drop_index("idx_media_assets_owner_status", table_name="media_assets")
    op.drop_table("media_assets")

    bind = op.get_bind()
    media_moderation_status.drop(bind, checkfirst=True)
    media_status.drop(bind, checkfirst=True)
    media_visibility.drop(bind, checkfirst=True)
    media_purpose.drop(bind, checkfirst=True)
