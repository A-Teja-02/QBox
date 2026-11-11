from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, security_scheme
from app.db.session import get_db
from app.models.models import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    ShopkeeperRegisterRequest,
    ShopkeeperRegisterResponse,
    TokenResponse,
    UserProfileResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register/shopkeeper",
    response_model=ShopkeeperRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new shopkeeper account and shop with mandatory payment QR",
)
async def register_shopkeeper(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ShopkeeperRegisterResponse:
    """
    Registers a new shopkeeper user account, shopkeeper profile, and shop
    within an atomic database transaction. Supports multipart/form-data upload
    for mandatory static UPI payment QR image or JSON payload.
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        full_name = form.get("full_name")
        shop_name = form.get("shop_name")
        shop_address = form.get("shop_address")
        phone = form.get("phone")
        password = form.get("password") or "DemoPass@123"
        email = form.get("email")
        upi_id = form.get("upi_id")
        payment_qr_file = form.get("payment_qr_image") or form.get("payment_qr_file") or form.get("qr_image")

        if not payment_qr_file or not hasattr(payment_qr_file, "read"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Payment QR image is mandatory for new shopkeeper registration. Please upload your static UPI QR image from gallery.",
            )

        file_bytes = await payment_qr_file.read()
        filename = getattr(payment_qr_file, "filename", "payment_qr.png") or "payment_qr.png"

        try:
            req = ShopkeeperRegisterRequest(
                full_name=str(full_name) if full_name else "",
                shop_name=str(shop_name) if shop_name else "",
                shop_address=str(shop_address) if shop_address else "",
                phone=str(phone) if phone else "",
                password=str(password),
                email=str(email) if email else None,
                upi_id=str(upi_id) if upi_id else None,
            )
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

        return await AuthService.register_shopkeeper(
            db=db,
            req=req,
            payment_qr_file=(file_bytes, filename),
        )
    else:
        # JSON payload
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON request body")

        try:
            req = ShopkeeperRegisterRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

        payment_qr_tuple = None
        if req.payment_qr_base64:
            import base64
            try:
                b = base64.b64decode(req.payment_qr_base64)
                payment_qr_tuple = (b, "payment_qr.png")
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 payload for payment QR image")

        return await AuthService.register_shopkeeper(
            db=db,
            req=req,
            payment_qr_file=payment_qr_tuple,
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in using mobile number or email and password",
)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticates a user via phone or email and password.
    Returns access and refresh tokens along with user roles.
    """
    return await AuthService.login(db=db, req=req)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using a valid refresh token",
)
async def refresh_token(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Issues a fresh access token and refresh token using an unexpired refresh token.
    """
    return await AuthService.refresh_access_token(db=db, refresh_token=req.refresh_token)


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Returns the authenticated user's profile and roles."""
    return await AuthService.get_current_user_profile(db=db, user_id=current_user.id)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and invalidate session server-side",
)
async def logout(
    req: Optional[LogoutRequest] = None,
    current_user: User = Depends(get_current_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Invalidates the active session server-side in PostgreSQL.
    Immediately revokes the access token used for this request, preventing reuse.
    Optionally revokes all active sessions or a specific refresh token session.
    """
    refresh_token = req.refresh_token if req else None
    all_sessions = req.all_sessions if req else False
    raw_access_token = credentials.credentials if credentials else None
    return await AuthService.logout(
        db=db,
        current_user=current_user,
        raw_access_token=raw_access_token,
        refresh_token=refresh_token,
        all_sessions=all_sessions,
    )

