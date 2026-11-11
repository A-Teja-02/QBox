"""
Udhaar Ledger Service (Phase 2).
Handles financial business logic, concurrency control, strict lock ordering,
complete-payload idempotency, and PostgreSQL deadlock retries.
"""

import asyncio
from datetime import datetime, timezone
import random
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.db.session import AsyncSessionLocal
from app.models.models import LedgerEntry, Shop, ShopCustomer
from app.schemas.ledger import CreateLedgerEntryRequest, CreateReversalRequest

T = TypeVar("T")

MAX_DEADLOCK_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.05


def _match_canonical_payload(
    entry: LedgerEntry,
    customer_user_id: uuid.UUID,
    transaction_type: str,
    amount_paise: int,
    note: Optional[str],
    original_entry_id: Optional[uuid.UUID],
) -> bool:
    """
    Compares all canonical transaction fields to verify exact idempotent replay.
    Whitespace in notes is normalized before comparison.
    """
    norm_entry_note = entry.note.strip() if entry.note else None
    norm_req_note = note.strip() if note else None
    return (
        entry.customer_user_id == customer_user_id
        and entry.transaction_type == transaction_type
        and entry.amount_paise == amount_paise
        and norm_entry_note == norm_req_note
        and entry.original_entry_id == original_entry_id
    )


async def execute_with_deadlock_retry(
    session_factory: Callable[[], AsyncSession],
    operation_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Executes a database operation inside an atomic session with automatic deadlock retry.
    Catches PostgreSQL 40P01 DeadlockDetected, safely rolls back, applies exponential
    backoff with randomized jitter, and retries with a fresh transaction session.
    """
    for attempt in range(MAX_DEADLOCK_RETRIES + 1):
        async with session_factory() as session:
            try:
                result = await operation_fn(session, *args, **kwargs)
                return result
            except DBAPIError as exc:
                await session.rollback()
                orig = getattr(exc, "orig", None)
                sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
                is_deadlock = (
                    "deadlock detected" in str(exc).lower()
                    or sqlstate == "40P01"
                )
                if is_deadlock and attempt < MAX_DEADLOCK_RETRIES:
                    backoff = (BASE_BACKOFF_SECONDS * (2 ** attempt)) + random.uniform(0.01, 0.04)
                    await asyncio.sleep(backoff)
                    continue
                raise
            except Exception:
                await session.rollback()
                raise


class LedgerService:
    """
    Authoritative service managing all Udhaar ledger operations.
    Enforces strict lock ordering (ShopCustomer -> LedgerEntry), per-customer
    monotonically increasing sequence numbers, and immutable balance snapshots.
    """

    @classmethod
    async def record_transaction(
        cls,
        db: AsyncSession,
        shop_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        req: CreateLedgerEntryRequest,
    ) -> Tuple[LedgerEntry, int, bool]:
        """
        Records a CREDIT or REPAYMENT entry for a customer.
        Returns: (entry, current_balance_paise, is_idempotent_replay)
        """
        # 1. Authorize: Verify shop exists and is owned by the authenticated caller
        shop = (await db.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found.",
            )
        if shop.owner_user_id != created_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the shop owner can record ledger transactions for this shop.",
            )

        # 2. Strict Lock Step 1: Exclusively lock the ShopCustomer account row
        sc_stmt = (
            select(ShopCustomer)
            .where(
                ShopCustomer.shop_id == shop_id,
                ShopCustomer.customer_user_id == customer_user_id,
            )
            .options(
                undefer(ShopCustomer.current_balance_paise),
                undefer(ShopCustomer.last_entry_sequence),
            )
            .with_for_update()
        )
        shop_customer = (await db.execute(sc_stmt)).scalar_one_or_none()
        if not shop_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer has not joined this shop.",
            )
        if shop_customer.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer membership is not ACTIVE.",
            )

        # 3. Complete Canonical Idempotency Check
        existing_stmt = select(LedgerEntry).where(
            LedgerEntry.shop_id == shop_id,
            LedgerEntry.idempotency_key == req.idempotency_key,
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            if _match_canonical_payload(
                entry=existing,
                customer_user_id=customer_user_id,
                transaction_type=req.transaction_type,
                amount_paise=req.amount_paise,
                note=req.note,
                original_entry_id=None,
            ):
                return existing, shop_customer.current_balance_paise, True
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Idempotency key '{req.idempotency_key}' already used with a different payload.",
            )

        # 4. Enforce Financial Invariant: Repayment cannot exceed outstanding balance
        if req.transaction_type == "REPAYMENT":
            if req.amount_paise > shop_customer.current_balance_paise:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Repayment amount {req.amount_paise} paise exceeds "
                        f"current outstanding balance {shop_customer.current_balance_paise} paise."
                    ),
                )

        # 5. Compute Monotonic Per-Customer Sequence & Immutable Balance Snapshot
        new_sequence = (shop_customer.last_entry_sequence or 0) + 1
        if req.transaction_type == "CREDIT":
            new_balance = shop_customer.current_balance_paise + req.amount_paise
        else:
            new_balance = shop_customer.current_balance_paise - req.amount_paise

        shop_customer.last_entry_sequence = new_sequence
        shop_customer.current_balance_paise = new_balance

        # 6. Instantiate new immutable LedgerEntry
        new_entry = LedgerEntry(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=customer_user_id,
            created_by_user_id=created_by_user_id,
            transaction_type=req.transaction_type,
            amount_paise=req.amount_paise,
            note=req.note.strip() if req.note else None,
            idempotency_key=req.idempotency_key,
            original_entry_id=None,
            sequence_number=new_sequence,
            balance_after_transaction_paise=new_balance,
            created_at=datetime.now(timezone.utc),
        )

        # 7. Insert with SAVEPOINT to safely handle concurrent unique constraint races
        try:
            async with db.begin_nested():
                db.add(new_entry)
                await db.flush()
        except IntegrityError as exc:
            err_str = str(exc).lower()
            if "uq_ledger_shop_idempotency_key" in err_str:
                race_stmt = select(LedgerEntry).where(
                    LedgerEntry.shop_id == shop_id,
                    LedgerEntry.idempotency_key == req.idempotency_key,
                )
                committed_entry = (await db.execute(race_stmt)).scalar_one_or_none()
                if committed_entry and _match_canonical_payload(
                    entry=committed_entry,
                    customer_user_id=customer_user_id,
                    transaction_type=req.transaction_type,
                    amount_paise=req.amount_paise,
                    note=req.note,
                    original_entry_id=None,
                ):
                    return committed_entry, shop_customer.current_balance_paise, True
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Idempotency key '{req.idempotency_key}' conflict with concurrent transaction.",
                )
            raise

        await db.commit()
        await db.refresh(new_entry)
        return new_entry, new_balance, False

    @classmethod
    async def record_reversal(
        cls,
        db: AsyncSession,
        shop_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        req: CreateReversalRequest,
    ) -> Tuple[LedgerEntry, int, bool]:
        """
        Records a CREDIT_REVERSAL or REPAYMENT_REVERSAL entry referencing an original transaction.
        Enforces strict two-tier lock ordering (ShopCustomer first, original LedgerEntry second).
        Returns: (entry, current_balance_paise, is_idempotent_replay)
        """
        # 1. Authorize: Verify shop exists and caller is owner
        shop = (await db.execute(select(Shop).where(Shop.id == shop_id))).scalar_one_or_none()
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found.",
            )
        if shop.owner_user_id != created_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the shop owner can record ledger transactions for this shop.",
            )

        # 2. Strict Lock Step 1: Exclusively lock the ShopCustomer account row FIRST
        sc_stmt = (
            select(ShopCustomer)
            .where(
                ShopCustomer.shop_id == shop_id,
                ShopCustomer.customer_user_id == customer_user_id,
            )
            .options(
                undefer(ShopCustomer.current_balance_paise),
                undefer(ShopCustomer.last_entry_sequence),
            )
            .with_for_update()
        )
        shop_customer = (await db.execute(sc_stmt)).scalar_one_or_none()
        if not shop_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer has not joined this shop.",
            )
        if shop_customer.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer membership is not ACTIVE.",
            )

        # 3. Complete Canonical Idempotency Check
        existing_stmt = select(LedgerEntry).where(
            LedgerEntry.shop_id == shop_id,
            LedgerEntry.idempotency_key == req.idempotency_key,
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            if _match_canonical_payload(
                entry=existing,
                customer_user_id=customer_user_id,
                transaction_type=req.transaction_type,
                amount_paise=req.amount_paise,
                note=req.note,
                original_entry_id=req.original_entry_id,
            ):
                return existing, shop_customer.current_balance_paise, True
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Idempotency key '{req.idempotency_key}' already used with a different payload.",
            )

        # 4. Strict Lock Step 2: Exclusively lock the Original LedgerEntry SECOND
        orig_stmt = (
            select(LedgerEntry)
            .where(LedgerEntry.id == req.original_entry_id)
            .with_for_update()
        )
        orig_entry = (await db.execute(orig_stmt)).scalar_one_or_none()
        if not orig_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original ledger entry {req.original_entry_id} not found.",
            )

        # 5. Validate Tenant & Customer Identity Match
        if orig_entry.shop_id != shop_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Reversal shop_id ({shop_id}) does not match "
                    f"original entry shop_id ({orig_entry.shop_id})."
                ),
            )
        if orig_entry.customer_user_id != customer_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Reversal customer_user_id ({customer_user_id}) does not match "
                    f"original entry customer_user_id ({orig_entry.customer_user_id})."
                ),
            )

        # 6. Validate Transaction Type Pairing
        if req.transaction_type == "CREDIT_REVERSAL" and orig_entry.transaction_type != "CREDIT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CREDIT_REVERSAL can only reverse a CREDIT entry (original is {orig_entry.transaction_type}).",
            )
        if req.transaction_type == "REPAYMENT_REVERSAL" and orig_entry.transaction_type != "REPAYMENT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"REPAYMENT_REVERSAL can only reverse a REPAYMENT entry (original is {orig_entry.transaction_type}).",
            )

        # 7. Validate Cumulative Reversal Cap
        sum_stmt = select(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).where(
            LedgerEntry.original_entry_id == req.original_entry_id
        )
        already_reversed = (await db.execute(sum_stmt)).scalar() or 0
        remaining_reversible = orig_entry.amount_paise - already_reversed

        if (already_reversed + req.amount_paise) > orig_entry.amount_paise:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Reversal amount {req.amount_paise} paise exceeds remaining reversible amount "
                    f"{remaining_reversible} paise (original: {orig_entry.amount_paise} paise, "
                    f"already reversed: {already_reversed} paise)."
                ),
            )

        # 8. Requirement 5: Enforce Credit Reversal Outstanding Balance Restriction
        if req.transaction_type == "CREDIT_REVERSAL":
            if req.amount_paise > shop_customer.current_balance_paise:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Credit reversal amount {req.amount_paise} paise exceeds current customer balance "
                        f"{shop_customer.current_balance_paise} paise. The customer has already repaid "
                        "part or all of this credit."
                    ),
                )

        # 9. Compute Monotonic Per-Customer Sequence & Immutable Balance Snapshot
        new_sequence = (shop_customer.last_entry_sequence or 0) + 1
        if req.transaction_type == "CREDIT_REVERSAL":
            new_balance = shop_customer.current_balance_paise - req.amount_paise
        else:
            new_balance = shop_customer.current_balance_paise + req.amount_paise

        shop_customer.last_entry_sequence = new_sequence
        shop_customer.current_balance_paise = new_balance

        # 10. Instantiate new immutable reversal LedgerEntry
        new_entry = LedgerEntry(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=customer_user_id,
            created_by_user_id=created_by_user_id,
            transaction_type=req.transaction_type,
            amount_paise=req.amount_paise,
            note=req.note.strip() if req.note else None,
            idempotency_key=req.idempotency_key,
            original_entry_id=req.original_entry_id,
            sequence_number=new_sequence,
            balance_after_transaction_paise=new_balance,
            created_at=datetime.now(timezone.utc),
        )

        # 11. Insert with SAVEPOINT to safely handle concurrent unique constraint races
        try:
            async with db.begin_nested():
                db.add(new_entry)
                await db.flush()
        except IntegrityError as exc:
            err_str = str(exc).lower()
            if "uq_ledger_shop_idempotency_key" in err_str:
                race_stmt = select(LedgerEntry).where(
                    LedgerEntry.shop_id == shop_id,
                    LedgerEntry.idempotency_key == req.idempotency_key,
                )
                committed_entry = (await db.execute(race_stmt)).scalar_one_or_none()
                if committed_entry and _match_canonical_payload(
                    entry=committed_entry,
                    customer_user_id=customer_user_id,
                    transaction_type=req.transaction_type,
                    amount_paise=req.amount_paise,
                    note=req.note,
                    original_entry_id=req.original_entry_id,
                ):
                    return committed_entry, shop_customer.current_balance_paise, True
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Idempotency key '{req.idempotency_key}' conflict with concurrent transaction.",
                )
            raise

        await db.commit()
        await db.refresh(new_entry)
        return new_entry, new_balance, False

    @classmethod
    async def record_transaction_with_retry(
        cls,
        shop_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        req: CreateLedgerEntryRequest,
        session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
    ) -> Tuple[LedgerEntry, int, bool]:
        """Wraps record_transaction in execute_with_deadlock_retry."""
        return await execute_with_deadlock_retry(
            session_factory,
            cls.record_transaction,
            shop_id,
            customer_user_id,
            created_by_user_id,
            req,
        )

    @classmethod
    async def record_reversal_with_retry(
        cls,
        shop_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        req: CreateReversalRequest,
        session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
    ) -> Tuple[LedgerEntry, int, bool]:
        """Wraps record_reversal in execute_with_deadlock_retry."""
        return await execute_with_deadlock_retry(
            session_factory,
            cls.record_reversal,
            shop_id,
            customer_user_id,
            created_by_user_id,
            req,
        )

    @classmethod
    async def get_customer_ledger(
        cls,
        db: AsyncSession,
        shop_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Retrieves paginated ledger history for a specific customer at a shop,
        ordered strictly by sequence_number DESC (newest to oldest).
        """
        sc_stmt = (
            select(ShopCustomer)
            .where(
                ShopCustomer.shop_id == shop_id,
                ShopCustomer.customer_user_id == customer_user_id,
            )
            .options(
                undefer(ShopCustomer.current_balance_paise),
                undefer(ShopCustomer.last_entry_sequence),
            )
        )
        shop_customer = (await db.execute(sc_stmt)).scalar_one_or_none()
        if not shop_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer has not joined this shop.",
            )

        # Count total ledger entries
        count_stmt = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.shop_id == shop_id,
            LedgerEntry.customer_user_id == customer_user_id,
        )
        total_count = (await db.execute(count_stmt)).scalar() or 0

        # Query entries ordered by sequence_number DESC
        entries_stmt = (
            select(LedgerEntry)
            .where(
                LedgerEntry.shop_id == shop_id,
                LedgerEntry.customer_user_id == customer_user_id,
            )
            .order_by(LedgerEntry.sequence_number.desc())
            .limit(limit)
            .offset(offset)
        )
        entries = (await db.execute(entries_stmt)).scalars().all()

        return {
            "items": list(entries),
            "total_count": total_count,
            "current_balance_paise": shop_customer.current_balance_paise,
            "last_entry_sequence": shop_customer.last_entry_sequence,
        }

    @classmethod
    async def get_customer_global_summary(
        cls,
        db: AsyncSession,
        customer_user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Retrieves aggregated ledger summary across all shops joined by the customer.
        Calculates total outstanding Udhaar balance across shops.
        """
        sc_stmt = (
            select(ShopCustomer)
            .join(Shop, ShopCustomer.shop_id == Shop.id)
            .where(
                ShopCustomer.customer_user_id == customer_user_id,
                ShopCustomer.status == "ACTIVE",
            )
            .options(
                undefer(ShopCustomer.current_balance_paise),
                undefer(ShopCustomer.last_entry_sequence),
                selectinload(ShopCustomer.shop),
            )
        )
        shop_customers = (await db.execute(sc_stmt)).scalars().all()

        # Fetch latest transaction timestamp per shop for this customer
        last_tx_stmt = (
            select(LedgerEntry.shop_id, func.max(LedgerEntry.created_at))
            .where(LedgerEntry.customer_user_id == customer_user_id)
            .group_by(LedgerEntry.shop_id)
        )
        last_tx_res = await db.execute(last_tx_stmt)
        last_tx_map = dict(last_tx_res.all())

        shops_list = []
        total_outstanding = 0
        for sc in shop_customers:
            total_outstanding += sc.current_balance_paise
            shops_list.append({
                "shop_id": sc.shop_id,
                "shop_name": sc.shop.shop_name if sc.shop else "Shop",
                "current_balance_paise": sc.current_balance_paise,
                "last_entry_sequence": sc.last_entry_sequence,
                "last_transaction_at": last_tx_map.get(sc.shop_id),
            })

        return {
            "total_outstanding_paise": total_outstanding,
            "shops": shops_list,
        }

