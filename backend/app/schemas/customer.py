from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class JoinShopRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Raw scanned token from the QR code")


class JoinShopResponse(BaseModel):
    status: str = Field(..., description="'joined' or 'already_joined'")
    shop_id: str
    shop_name: str
    shop_address: str
    joined_at: datetime


class CustomerShopResponse(BaseModel):
    shop_id: str
    shop_name: str
    shop_address: str
    upi_id: Optional[str] = None
    joined_at: datetime


class ShopCustomerResponse(BaseModel):
    customer_user_id: str
    full_name: str
    phone: str
    joined_at: datetime
    current_balance_paise: int = 0


