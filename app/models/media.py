import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class MediaPurposeEnum(str, enum.Enum):
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    KYC_DOCUMENT = "KYC_DOCUMENT"


class MediaVisibilityEnum(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class MediaStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    ATTACHED = "ATTACHED"
    DELETION_PENDING = "DELETION_PENDING"
    DELETING = "DELETING"
    DELETED = "DELETED"


class MediaModerationStatusEnum(str, enum.Enum):
    NOT_REVIEWED = "NOT_REVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="media_assets_byte_size_check"),
        CheckConstraint("width > 0", name="media_assets_width_check"),
        CheckConstraint("height > 0", name="media_assets_height_check"),
        CheckConstraint(
            "purpose != 'KYC_DOCUMENT' OR visibility = 'PRIVATE'",
            name="media_assets_kyc_private_check",
        ),
        UniqueConstraint(
            "provider",
            "provider_public_id",
            name="uq_media_assets_provider_identity",
        ),
        Index("idx_media_assets_owner_status", "owner_id", "status"),
        Index("idx_media_assets_cleanup", "status", "delete_after"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider = Column(String(32), nullable=False, default="cloudinary")
    provider_public_id = Column(String(512), nullable=False)
    secure_url = Column(String(2048), nullable=False)
    purpose = Column(
        Enum(MediaPurposeEnum, name="media_purpose"),
        nullable=False,
    )
    visibility = Column(
        Enum(MediaVisibilityEnum, name="media_visibility"),
        nullable=False,
    )
    status = Column(
        Enum(MediaStatusEnum, name="media_status"),
        nullable=False,
        default=MediaStatusEnum.PENDING,
    )
    moderation_status = Column(
        Enum(MediaModerationStatusEnum, name="media_moderation_status"),
        nullable=False,
        default=MediaModerationStatusEnum.NOT_REVIEWED,
    )
    content_type = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    delete_after = Column(DateTime(timezone=True), nullable=True)
    attached_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
