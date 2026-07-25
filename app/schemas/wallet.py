from pydantic import BaseModel

class WalletDeposit(BaseModel):
    amount: float

class WalletResponse(BaseModel):
    balance: float
    currency: str

    class Config:
        from_attributes = True
