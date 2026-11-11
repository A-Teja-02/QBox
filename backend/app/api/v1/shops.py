import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, update
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_shop_by_id, require_role
from app.db.session import get_db
from app.models.models import Shop, ShopPaymentQr, User
from app.schemas.customer import JoinShopRequest, JoinShopResponse, ShopCustomerResponse
from app.schemas.qr import PaymentQrMetadataResponse, ShopRegistrationQrResponse
from app.services.customer_service import CustomerService
from app.services.qr_service import QrService
from app.services.storage_service import StorageService

router = APIRouter()


def _get_current_user_shop(current_user: User) -> Shop:
    if not current_user.shops or len(current_user.shops) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No shop registered for this shopkeeper account.",
        )
    return current_user.shops[0]


# --- Current Authenticated Shopkeeper Routes (/me) ---

@router.get(
    "/me/registration-qr",
    response_model=ShopRegistrationQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the registration QR code for the current authenticated shopkeeper",
)
async def get_my_shop_registration_qr(
    request: Request,
    device: Optional[str] = Query(None, description="Target environment override: 'physical' or 'emulator'"),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> ShopRegistrationQrResponse:
    """
    Returns the permanent static registration QR code and URL for the authenticated shopkeeper's shop.
    Dynamically encodes the reachable URL matching the request host or selected target environment.
    """
    shop = _get_current_user_shop(current_user)
    token_record, raw_token, reg_url, qr_svg = await QrService.get_or_create_active_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
        request=request,
        target_override=device,
    )
    return ShopRegistrationQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        registration_url=reg_url,
        qr_code_svg=qr_svg,
        is_active=token_record.is_active,
        created_at=token_record.created_at,
    )


@router.post(
    "/me/registration-qr/rotate",
    response_model=ShopRegistrationQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the registration QR code for the current authenticated shopkeeper",
)
async def rotate_my_shop_registration_qr(
    request: Request,
    device: Optional[str] = Query(None, description="Target environment override: 'physical' or 'emulator'"),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> ShopRegistrationQrResponse:
    """
    Atomically revokes current active token and generates a new registration QR code.
    """
    shop = _get_current_user_shop(current_user)
    new_token, raw_token, reg_url, qr_svg = await QrService.rotate_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
        request=request,
        target_override=device,
    )
    return ShopRegistrationQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        registration_url=reg_url,
        qr_code_svg=qr_svg,
        is_active=new_token.is_active,
        created_at=new_token.created_at,
    )


@router.post(
    "/me/registration-qr/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke the registration QR code for the current authenticated shopkeeper",
)
async def revoke_my_shop_registration_qr(
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revokes the active registration QR code for the authenticated shopkeeper's shop."""
    shop = _get_current_user_shop(current_user)
    await QrService.revoke_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
    )
    return {
        "status": "revoked",
        "shop_id": str(shop.id),
        "message": "Registration QR code has been permanently deactivated.",
    }


@router.get(
    "/me/customers",
    response_model=List[ShopCustomerResponse],
    status_code=status.HTTP_200_OK,
    summary="List all customers registered with the current authenticated shopkeeper's shop",
)
async def get_my_shop_customers(
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> List[ShopCustomerResponse]:
    """Retrieves all customers onboarded to the authenticated shopkeeper's shop."""
    shop = _get_current_user_shop(current_user)
    raw_customers = await CustomerService.get_shop_customers(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
    )
    return [ShopCustomerResponse(**c) for c in raw_customers]


# --- Explicit Shop ID Routes (/{shop_id}/...) ---


@router.get(
    "/{shop_id}/registration-qr",
    response_model=ShopRegistrationQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the permanent static registration QR code for a shop",
)
async def get_shop_registration_qr(
    shop_id: uuid.UUID,
    request: Request,
    device: Optional[str] = Query(None, description="Target environment override: 'physical' or 'emulator'"),
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> ShopRegistrationQrResponse:
    """
    Returns the permanent static registration QR code and URL for the shop.
    Verifies ownership. Token remains identical across logins and app restarts.
    """
    token_record, raw_token, reg_url, qr_svg = await QrService.get_or_create_active_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
        request=request,
        target_override=device,
    )
    return ShopRegistrationQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        registration_url=reg_url,
        qr_code_svg=qr_svg,
        is_active=token_record.is_active,
        created_at=token_record.created_at,
    )


@router.post(
    "/{shop_id}/registration-qr",
    response_model=ShopRegistrationQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Ensure the registration QR exists for a shop",
)
async def create_or_get_shop_registration_qr(
    shop_id: uuid.UUID,
    request: Request,
    device: Optional[str] = Query(None, description="Target environment override: 'physical' or 'emulator'"),
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> ShopRegistrationQrResponse:
    """Ensures active registration QR exists. Does not recreate if already active."""
    token_record, raw_token, reg_url, qr_svg = await QrService.get_or_create_active_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
        request=request,
        target_override=device,
    )
    return ShopRegistrationQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        registration_url=reg_url,
        qr_code_svg=qr_svg,
        is_active=token_record.is_active,
        created_at=token_record.created_at,
    )


@router.post(
    "/{shop_id}/registration-qr/rotate",
    response_model=ShopRegistrationQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the registration QR code for a shop",
)
async def rotate_shop_registration_qr(
    shop_id: uuid.UUID,
    request: Request,
    device: Optional[str] = Query(None, description="Target environment override: 'physical' or 'emulator'"),
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> ShopRegistrationQrResponse:
    """
    Atomically revokes the current active token and generates a new registration QR code.
    Old QR links stop working immediately.
    """
    new_token, raw_token, reg_url, qr_svg = await QrService.rotate_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
        request=request,
        target_override=device,
    )
    return ShopRegistrationQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        registration_url=reg_url,
        qr_code_svg=qr_svg,
        is_active=new_token.is_active,
        created_at=new_token.created_at,
    )


@router.post(
    "/{shop_id}/registration-qr/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke the registration QR code for a shop",
)
async def revoke_shop_registration_qr(
    shop_id: uuid.UUID,
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revokes the active registration QR code without creating a replacement."""
    await QrService.revoke_shop_qr(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
    )
    return {
        "status": "revoked",
        "shop_id": str(shop.id),
        "message": "Registration QR code has been permanently deactivated.",
    }


@router.get(
    "/{shop_id}/customers",
    response_model=List[ShopCustomerResponse],
    status_code=status.HTTP_200_OK,
    summary="List all customers registered with this shop",
)
async def get_shop_customers(
    shop_id: uuid.UUID,
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> List[ShopCustomerResponse]:
    """Retrieves all customers who have onboarded to this shop. Enforces tenant isolation."""
    raw_customers = await CustomerService.get_shop_customers(
        db=db,
        shop=shop,
        current_user_id=current_user.id,
    )
    return [ShopCustomerResponse(**c) for c in raw_customers]


@router.post(
    "/{shop_id}/join",
    response_model=JoinShopResponse,
    status_code=status.HTTP_200_OK,
    summary="Explicit customer confirmation to join a shop via scanned QR token",
)
async def join_shop(
    shop_id: uuid.UUID,
    req: JoinShopRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JoinShopResponse:
    """
    Customer joins a shop using the raw token extracted from the scanned QR code.
    Idempotent. Does NOT create any ledger or Udhaar transactions.
    """
    res = await CustomerService.join_shop_via_token(
        db=db,
        customer_user=current_user,
        shop_id=shop_id,
        raw_token=req.token,
    )
    return JoinShopResponse(**res)


# --- Helper Functions for Payment QR Management ---

def _verify_shop_owner(shop: Shop, current_user: User) -> None:
    if shop.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this shop's payment QR code.",
        )


async def _get_shop_active_payment_qr_meta(db: AsyncSession, shop: Shop) -> PaymentQrMetadataResponse:
    query = select(ShopPaymentQr).where(
        ShopPaymentQr.shop_id == shop.id,
        ShopPaymentQr.is_active == True,
    )
    result = await db.execute(query)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active payment QR code found for this shop.",
        )
    return PaymentQrMetadataResponse(
        id=record.id,
        shop_id=record.shop_id,
        original_filename=record.original_filename,
        content_type=record.content_type,
        file_size_bytes=record.file_size_bytes,
        upi_provider=record.upi_provider,
        image_url=f"/api/v1/shops/{shop.id}/payment-qr/image",
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _save_or_replace_shop_payment_qr(
    db: AsyncSession,
    shop: Shop,
    payment_qr_image: UploadFile,
) -> PaymentQrMetadataResponse:
    file_bytes = await payment_qr_image.read()
    filename = getattr(payment_qr_image, "filename", "payment_qr.png") or "payment_qr.png"

    qr_meta = StorageService.save_payment_qr(
        shop_id=shop.id,
        file_bytes=file_bytes,
        original_filename=filename,
    )

    try:
        # 1. Soft-deactivate previous active QRs and clear historical binary data to conserve storage
        # Historical metadata (filename, size, checksum, upi_provider, timestamps) is preserved!
        await db.execute(
            update(ShopPaymentQr)
            .where(ShopPaymentQr.shop_id == shop.id, ShopPaymentQr.is_active == True)
            .values(is_active=False, image_data=None)
        )

        # 2. Insert new record with image_data BYTEA
        new_record = ShopPaymentQr(
            id=uuid.uuid4(),
            shop_id=shop.id,
            storage_key=qr_meta["storage_key"],
            original_filename=qr_meta["original_filename"],
            content_type=qr_meta["content_type"],
            file_size_bytes=qr_meta["file_size_bytes"],
            file_checksum=qr_meta["file_checksum"],
            upi_provider=qr_meta["upi_provider"],
            is_active=True,
            image_data=file_bytes,
        )
        db.add(new_record)

        # Auto-populate detected UPI ID if not already set
        if not shop.upi_id and qr_meta.get("detected_upi_id"):
            shop.upi_id = qr_meta["detected_upi_id"]
        shop.qr_image_path = f"/api/v1/shops/{shop.id}/payment-qr/image"

        await db.commit()
        await db.refresh(new_record)
    except Exception:
        await db.rollback()
        raise

    return PaymentQrMetadataResponse(
        id=new_record.id,
        shop_id=new_record.shop_id,
        original_filename=new_record.original_filename,
        content_type=new_record.content_type,
        file_size_bytes=new_record.file_size_bytes,
        upi_provider=new_record.upi_provider,
        image_url=f"/api/v1/shops/{shop.id}/payment-qr/image",
        is_active=new_record.is_active,
        created_at=new_record.created_at,
        updated_at=new_record.updated_at,
    )


async def _deactivate_shop_payment_qr(db: AsyncSession, shop: Shop) -> dict:
    await db.execute(
        update(ShopPaymentQr)
        .where(ShopPaymentQr.shop_id == shop.id, ShopPaymentQr.is_active == True)
        .values(is_active=False, image_data=None)
    )
    shop.qr_image_path = None
    await db.commit()
    return {"status": "deactivated", "shop_id": str(shop.id), "message": "Payment QR code has been removed."}


async def _stream_shop_payment_qr_image(db: AsyncSession, shop: Shop) -> Response:
    query = (
        select(ShopPaymentQr)
        .options(undefer(ShopPaymentQr.image_data))
        .where(
            ShopPaymentQr.shop_id == shop.id,
            ShopPaymentQr.is_active == True,
        )
    )
    result = await db.execute(query)
    record = result.scalar_one_or_none()
    if not record or not record.image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active payment QR code found for this shop.",
        )
    return Response(
        content=record.image_data,
        media_type=record.content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{record.original_filename}"',
        },
    )


# --- Shopkeeper Payment QR Management Endpoints ---

@router.get(
    "/me/payment-qr",
    response_model=PaymentQrMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active static payment QR metadata for authenticated shopkeeper",
)
async def get_my_payment_qr(
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> PaymentQrMetadataResponse:
    shop = _get_current_user_shop(current_user)
    return await _get_shop_active_payment_qr_meta(db=db, shop=shop)


@router.put(
    "/me/payment-qr",
    response_model=PaymentQrMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload or replace static payment QR image for authenticated shopkeeper",
)
async def update_my_payment_qr(
    payment_qr_image: UploadFile = File(..., description="Static UPI QR image (PNG/JPG/JPEG, max 5 MB)"),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> PaymentQrMetadataResponse:
    shop = _get_current_user_shop(current_user)
    return await _save_or_replace_shop_payment_qr(
        db=db,
        shop=shop,
        payment_qr_image=payment_qr_image,
    )


@router.delete(
    "/me/payment-qr",
    status_code=status.HTTP_200_OK,
    summary="Remove active static payment QR for authenticated shopkeeper",
)
async def delete_my_payment_qr(
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    shop = _get_current_user_shop(current_user)
    return await _deactivate_shop_payment_qr(db=db, shop=shop)


@router.get(
    "/me/payment-qr/image",
    summary="Stream static payment QR image for authenticated shopkeeper",
)
async def stream_my_payment_qr_image(
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
):
    shop = _get_current_user_shop(current_user)
    return await _stream_shop_payment_qr_image(db=db, shop=shop)


@router.get(
    "/{shop_id}/payment-qr",
    response_model=PaymentQrMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active static payment QR metadata for a shop",
)
async def get_shop_payment_qr(
    shop_id: uuid.UUID,
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> PaymentQrMetadataResponse:
    _verify_shop_owner(shop, current_user)
    return await _get_shop_active_payment_qr_meta(db=db, shop=shop)


@router.put(
    "/{shop_id}/payment-qr",
    response_model=PaymentQrMetadataResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload or replace static payment QR image for a shop",
)
async def update_shop_payment_qr(
    shop_id: uuid.UUID,
    payment_qr_image: UploadFile = File(..., description="Static UPI QR image (PNG/JPG/JPEG, max 5 MB)"),
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> PaymentQrMetadataResponse:
    _verify_shop_owner(shop, current_user)
    return await _save_or_replace_shop_payment_qr(
        db=db,
        shop=shop,
        payment_qr_image=payment_qr_image,
    )


@router.delete(
    "/{shop_id}/payment-qr",
    status_code=status.HTTP_200_OK,
    summary="Remove active static payment QR for a shop",
)
async def delete_shop_payment_qr(
    shop_id: uuid.UUID,
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _verify_shop_owner(shop, current_user)
    return await _deactivate_shop_payment_qr(db=db, shop=shop)


@router.get(
    "/{shop_id}/payment-qr/image",
    summary="Stream static payment QR image for a shop",
)
async def stream_shop_payment_qr_image(
    shop_id: uuid.UUID,
    shop: Shop = Depends(get_shop_by_id),
    current_user: User = Depends(require_role("SHOPKEEPER")),
    db: AsyncSession = Depends(get_db),
):
    _verify_shop_owner(shop, current_user)
    return await _stream_shop_payment_qr_image(db=db, shop=shop)

