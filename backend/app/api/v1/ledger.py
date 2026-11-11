"""
FastAPI router for Udhaar Ledger operations (Phase 2).
Exposes shopkeeper entry & reversal endpoints, customer history & summaries.
"""

from typing import Callable, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import AsyncSessionLocal, get_db, get_session_factory
from app.models.models import Shop, User
from app.schemas.ledger import (
    CreateLedgerEntryRequest,
    CreateReversalRequest,
    GlobalCustomerLedgerSummaryResponse,
    LedgerEntryResponse,
    LedgerHistoryResponse,
    LedgerTransactionResultResponse,
)
from app.services.ledger_service import LedgerService

router = APIRouter()


async def _verify_shop_ownership(shop_id: uuid.UUID, current_user: User, db: AsyncSession) -> Shop:
    """Verifies that the shop exists and is owned by the current authenticated user."""
    stmt = select(Shop).where(Shop.id == shop_id)
    shop = (await db.execute(stmt)).scalar_one_or_none()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found.",
        )
    if shop.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the shop owner can manage ledger transactions for this shop.",
        )
    return shop


# ==============================================================================
# SHOPKEEPER ENDPOINTS
# ==============================================================================

@router.post(
    "/shops/{shop_id}/ledger/entries",
    response_model=LedgerTransactionResultResponse,
    summary="Record a credit or repayment entry",
)
@router.post(
    "/shops/{shop_id}/ledger/customers/{customer_user_id}/entries",
    response_model=LedgerTransactionResultResponse,
    summary="Record a credit or repayment entry for a specific customer",
)
async def record_ledger_entry(
    shop_id: uuid.UUID,
    req: CreateLedgerEntryRequest,
    response: Response,
    customer_user_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    session_factory: Callable[[], AsyncSession] = Depends(get_session_factory),
):
    """
    Records a financial CREDIT or REPAYMENT entry.
    Returns HTTP 201 Created for new transactions.
    Returns HTTP 200 OK for exact canonical idempotent replays.
    Returns HTTP 409 Conflict if idempotency key was previously used with a different payload.
    """
    target_customer_id = customer_user_id or req.customer_user_id
    if not target_customer_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_user_id must be provided in the request body or path.",
        )

    entry, current_balance, is_replay = await LedgerService.record_transaction_with_retry(
        shop_id=shop_id,
        customer_user_id=target_customer_id,
        created_by_user_id=current_user.id,
        req=req,
        session_factory=session_factory,
    )

    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED

    return LedgerTransactionResultResponse(
        entry=LedgerEntryResponse.model_validate(entry),
        current_balance_paise=current_balance,
        is_idempotent_replay=is_replay,
    )


@router.post(
    "/shops/{shop_id}/ledger/reversals",
    response_model=LedgerTransactionResultResponse,
    summary="Record a reversal entry",
)
@router.post(
    "/shops/{shop_id}/ledger/customers/{customer_user_id}/reversals",
    response_model=LedgerTransactionResultResponse,
    summary="Record a reversal entry for a specific customer",
)
async def record_ledger_reversal(
    shop_id: uuid.UUID,
    req: CreateReversalRequest,
    response: Response,
    customer_user_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    session_factory: Callable[[], AsyncSession] = Depends(get_session_factory),
):
    """
    Records a CREDIT_REVERSAL or REPAYMENT_REVERSAL entry referencing an original entry.
    Enforces strict two-tier lock ordering (ShopCustomer first, original LedgerEntry second).
    Returns HTTP 201 Created for new transactions.
    Returns HTTP 200 OK for exact canonical idempotent replays.
    Returns HTTP 409 Conflict if idempotency key was previously used with a different payload.
    """
    target_customer_id = customer_user_id or req.customer_user_id
    if not target_customer_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_user_id must be provided in the request body or path.",
        )

    entry, current_balance, is_replay = await LedgerService.record_reversal_with_retry(
        shop_id=shop_id,
        customer_user_id=target_customer_id,
        created_by_user_id=current_user.id,
        req=req,
        session_factory=session_factory,
    )

    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED

    return LedgerTransactionResultResponse(
        entry=LedgerEntryResponse.model_validate(entry),
        current_balance_paise=current_balance,
        is_idempotent_replay=is_replay,
    )


@router.get(
    "/shops/{shop_id}/ledger/customers/{customer_user_id}",
    response_model=LedgerHistoryResponse,
    summary="Retrieve customer ledger history (Shopkeeper view)",
)
async def get_shop_customer_ledger(
    shop_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves paginated ledger history for a specific customer, ordered by sequence_number DESC."""
    await _verify_shop_ownership(shop_id, current_user, db)

    result = await LedgerService.get_customer_ledger(
        db=db,
        shop_id=shop_id,
        customer_user_id=customer_user_id,
        limit=limit,
        offset=offset,
    )
    return LedgerHistoryResponse(
        items=[LedgerEntryResponse.model_validate(item) for item in result["items"]],
        total_count=result["total_count"],
        current_balance_paise=result["current_balance_paise"],
        last_entry_sequence=result["last_entry_sequence"],
    )


# ==============================================================================
# CUSTOMER ENDPOINTS
# ==============================================================================

@router.get(
    "/customer/shops/{shop_id}/ledger",
    response_model=LedgerHistoryResponse,
    summary="Retrieve customer's own ledger history at a specific shop",
)
async def get_customer_shop_ledger(
    shop_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customer-facing endpoint to view their own ledger history and point-in-time balances at a shop."""
    result = await LedgerService.get_customer_ledger(
        db=db,
        shop_id=shop_id,
        customer_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return LedgerHistoryResponse(
        items=[LedgerEntryResponse.model_validate(item) for item in result["items"]],
        total_count=result["total_count"],
        current_balance_paise=result["current_balance_paise"],
        last_entry_sequence=result["last_entry_sequence"],
    )


@router.get(
    "/customer/ledger/summary",
    response_model=GlobalCustomerLedgerSummaryResponse,
    summary="Retrieve aggregated ledger summary across all shops",
)
async def get_customer_global_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customer-facing endpoint providing total outstanding Udhaar balance across all joined shops."""
    result = await LedgerService.get_customer_global_summary(
        db=db,
        customer_user_id=current_user.id,
    )
    return GlobalCustomerLedgerSummaryResponse(
        total_outstanding_paise=result["total_outstanding_paise"],
        shops=result["shops"],
    )
