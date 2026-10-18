from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PublicImageUploadResponse(BaseModel):
    asset_id: UUID
    url: str
    expires_at: datetime
