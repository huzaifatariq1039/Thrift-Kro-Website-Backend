from pydantic import BaseModel

class WalletResponse(BaseModel):
    balance: float
    currency: str

    class Config:
        from_attributes = True
