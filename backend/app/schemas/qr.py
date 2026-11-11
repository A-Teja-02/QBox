import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ShopRegistrationQrResponse(BaseModel):
    shop_id: uuid.UUID
    shop_name: str
    registration_url: str = Field(..., description="Canonical URL encoded inside the QR code")
    qr_code_svg: str = Field(..., description="SVG XML string representing the QR code")
    is_active: bool
    created_at: datetime


class PublicShopInfoResponse(BaseModel):
    shop_id: uuid.UUID
    shop_name: str
    shop_address: str
    is_valid: bool = True


class PaymentQrMetadataResponse(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    original_filename: str
    content_type: str
    file_size_bytes: int
    upi_provider: Optional[str] = None
    image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerPaymentQrResponse(BaseModel):
    shop_id: uuid.UUID
    shop_name: str
    upi_id: Optional[str] = None
    has_payment_qr: bool
    payment_qr_url: Optional[str] = None
    upi_provider: Optional[str] = None
    disclaimer: str = (
        "Scan or pay using any UPI app (GPay, PhonePe, Paytm, BHIM). "
        "Qbox does not hold or process customer funds; payments are made directly to the merchant."
    )

