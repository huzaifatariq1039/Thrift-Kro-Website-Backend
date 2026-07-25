from pydantic import BaseModel
from typing import Dict, Any

class AdminStatsResponse(BaseModel):
    users: Dict[str, Any]
    products: Dict[str, Any]
    orders: Dict[str, Any]
    revenue: Dict[str, Any]
