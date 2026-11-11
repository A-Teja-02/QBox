import re
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


def normalize_phone_number(raw_phone: str) -> str:
    """Normalizes phone numbers to standard E.164 +91XXXXXXXXXX format."""
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10:
        raise ValueError("Phone number must contain exactly 10 digits")
    if digits[0] not in "6789":
        raise ValueError("Indian mobile numbers must begin with 6, 7, 8, or 9")

    return f"+91{digits}"


def normalize_email_address(raw_email: Optional[str]) -> Optional[str]:
    """Normalizes email address to trimmed lowercase."""
    if not raw_email or not raw_email.strip():
        return None
    trimmed = raw_email.strip().lower()
    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    if not email_regex.match(trimmed):
        raise ValueError("Invalid email address format")
    return trimmed


class CustomerRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255, description="Full name of customer")
    phone: str = Field(..., description="10-digit mobile number")
    password: str = Field(default="DemoPass@123", min_length=6, description="Account password")
    address: Optional[str] = Field(default=None, description="Home / delivery address")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)


class ShopkeeperRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255, description="Full name of shopkeeper")
    shop_name: str = Field(..., min_length=2, max_length=255, description="Registered shop name")
    shop_address: str = Field(..., min_length=5, description="Full physical address of the shop")
    phone: str = Field(..., description="10-digit mobile number")
    password: str = Field(default="DemoPass@123", min_length=6, description="Account password")
    email: Optional[str] = Field(default=None, description="Optional email address")
    upi_id: Optional[str] = Field(default=None, description="Optional shop UPI address")
    qr_image_path: Optional[str] = Field(default=None, description="Optional path or filename of QR image")
    payment_qr_base64: Optional[str] = Field(default=None, description="Optional base64-encoded payment QR image for JSON payloads")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email_address(v)

    @field_validator("upi_id")
    @classmethod
    def validate_upi(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        trimmed = v.strip()
        upi_regex = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")
        if not upi_regex.match(trimmed):
            raise ValueError("Enter a valid UPI ID format (e.g. shopname@upi or 9876543210@paytm)")
        return trimmed


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    roles: List[str]
    user_id: str
    phone: str
    full_name: Optional[str] = None
    shop_id: Optional[uuid.UUID] = None
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid refresh token issued by Qbox auth service")


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(default=None, description="Optional refresh token to invalidate")
    all_sessions: bool = Field(default=False, description="Invalidate all active sessions for this user")


class ShopkeeperRegisterResponse(BaseModel):
    user_id: uuid.UUID
    phone: str
    email: Optional[str]
    full_name: str
    shop_id: uuid.UUID
    shop_name: str
    shop_address: str
    upi_id: Optional[str]
    qr_image_path: Optional[str]
    roles: List[str]
    created_at: datetime
    tokens: TokenResponse
    payment_qr_url: Optional[str] = None
    payment_qr_id: Optional[uuid.UUID] = None
    has_payment_qr: bool = False


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Mobile number (10-digit) or registered email address")
    password: str = Field(..., min_length=1, description="Account password")


class UserProfileResponse(BaseModel):
    user_id: uuid.UUID
    phone: str
    email: Optional[str]
    roles: List[str]
    full_name: Optional[str] = None
    shop_id: Optional[uuid.UUID] = None
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None
    created_at: datetime

