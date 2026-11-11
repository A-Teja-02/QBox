from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.qr import PublicShopInfoResponse
from app.services.qr_service import QrService
from app.services.rate_limiter import SharedRateLimiter

router = APIRouter()


@router.get(
    "/shops/join/{token}",
    response_model=PublicShopInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Public shop lookup from scanned QR token",
)
async def public_shop_lookup(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicShopInfoResponse:
    """
    Resolves a scanned raw QR token to safe public shop details.
    Protected by PostgreSQL-backed shared rate limiting against enumeration.
    Returns generic 404 if invalid, inactive, or revoked.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"rate:public_qr:{client_ip}"

    # Rate limiting: max 30 requests per minute per IP
    allowed = await SharedRateLimiter.check_rate_limit(
        db=db,
        key=rate_key,
        max_requests=30,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many lookup attempts. Please try again in a minute.",
        )

    shop = await QrService.lookup_public_shop_by_token(db=db, raw_token=token)
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration QR code is invalid or has expired.",
        )

    return PublicShopInfoResponse(
        shop_id=shop.id,
        shop_name=shop.shop_name,
        shop_address=shop.shop_address,
        is_valid=True,
    )

