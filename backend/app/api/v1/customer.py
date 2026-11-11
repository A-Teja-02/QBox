import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import Shop, ShopCustomer, ShopPaymentQr, User
from app.schemas.auth import CustomerRegisterRequest, TokenResponse
from app.schemas.customer import CustomerShopResponse
from app.schemas.qr import CustomerPaymentQrResponse
from app.services.auth_service import AuthService
from app.services.customer_service import CustomerService
from app.services.storage_service import StorageService

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
async def register_customer(
    req: CustomerRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Registers a new customer account and returns JWT tokens."""
    return await AuthService.register_customer(db=db, req=req)


@router.get(
    "/shops",
    response_model=List[CustomerShopResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all shops joined by the authenticated customer",
)
async def get_my_joined_shops(
    current_user: User = Depends(require_role("CUSTOMER")),
    db: AsyncSession = Depends(get_db),
) -> List[CustomerShopResponse]:
    """Retrieves all shops joined by this customer."""
    shops_data = await CustomerService.get_customer_joined_shops(
        db=db,
        customer_user_id=current_user.id,
    )
    return [CustomerShopResponse(**s) for s in shops_data]


@router.get(
    "/shops/{shop_id}/payment-qr",
    response_model=CustomerPaymentQrResponse,
    status_code=status.HTTP_200_OK,
    summary="Get static payment QR for a joined shop",
)
async def get_shop_payment_qr_for_customer(
    shop_id: uuid.UUID,
    current_user: User = Depends(require_role("CUSTOMER")),
    db: AsyncSession = Depends(get_db),
) -> CustomerPaymentQrResponse:
    """
    Retrieves the static UPI payment QR of a shop that this customer has joined.
    Strict tenant isolation: Rejects if the customer has not joined this shop.
    """
    # 1. Enforce active customer-shop relationship
    link_query = select(ShopCustomer).where(
        ShopCustomer.shop_id == shop_id,
        ShopCustomer.customer_user_id == current_user.id,
        ShopCustomer.status == "ACTIVE",
    )
    link_res = await db.execute(link_query)
    link = link_res.scalar_one_or_none()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to payment details for this shop. Please connect to the shop first.",
        )

    # 2. Retrieve Shop details
    shop_res = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_res.scalar_one_or_none()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found.",
        )

    # 3. Retrieve active Payment QR
    pqr_res = await db.execute(
        select(ShopPaymentQr).where(
            ShopPaymentQr.shop_id == shop_id,
            ShopPaymentQr.is_active == True,
        )
    )
    pqr = pqr_res.scalar_one_or_none()

    return CustomerPaymentQrResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        upi_id=shop.upi_id,
        has_payment_qr=pqr is not None,
        payment_qr_url=f"/api/v1/customer/shops/{shop.id}/payment-qr/image" if pqr else None,
        upi_provider=pqr.upi_provider if pqr else None,
    )


@router.get(
    "/shops/{shop_id}/payment-qr/image",
    summary="Stream static payment QR image for a joined shop",
)
async def stream_shop_payment_qr_image_for_customer(
    shop_id: uuid.UUID,
    current_user: User = Depends(require_role("CUSTOMER")),
    db: AsyncSession = Depends(get_db),
):
    """
    Streams the static UPI payment QR image for a connected customer.
    Enforces active membership check.
    """
    link_query = select(ShopCustomer).where(
        ShopCustomer.shop_id == shop_id,
        ShopCustomer.customer_user_id == current_user.id,
        ShopCustomer.status == "ACTIVE",
    )
    link_res = await db.execute(link_query)
    if not link_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You must be connected to this shop to view its payment QR.",
        )

    pqr_res = await db.execute(
        select(ShopPaymentQr)
        .options(undefer(ShopPaymentQr.image_data))
        .where(
            ShopPaymentQr.shop_id == shop_id,
            ShopPaymentQr.is_active == True,
        )
    )
    pqr = pqr_res.scalar_one_or_none()
    if not pqr or not pqr.image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active payment QR code found for this shop.",
        )

    return Response(
        content=pqr.image_data,
        media_type=pqr.content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{pqr.original_filename}"',
        },
    )

