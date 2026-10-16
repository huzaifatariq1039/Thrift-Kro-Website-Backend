from pydantic import BaseModel
from typing import Dict, Any

class AdminStatsResponse(BaseModel):
    users: Dict[str, Any]
    products: Dict[str, Any]
    orders: Dict[str, Any]
    revenue: Dict[str, Any]


# Backward-compatible import path for routers and external code.
from app.schemas.admin_reporting import (  # noqa: E402
    AdminStatsResponse as AdminStatsResponse,  # noqa: F811
)
