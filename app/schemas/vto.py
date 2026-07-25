from pydantic import BaseModel
from uuid import UUID

class VTORequest(BaseModel):
    product_id: UUID

class VTOResponse(BaseModel):
    composite_image_url: str
