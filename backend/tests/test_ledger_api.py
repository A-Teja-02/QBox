"""
Comprehensive API and Concurrency Tests for Qbox Udhaar Ledger (Phase 2).
Executes strictly within an isolated disposable PostgreSQL schema.

Covers:
1.  Record CREDIT success and balance update (201 Created, sequence 1, snapshot balance).
2.  Record REPAYMENT success and balance update (201 Created, sequence 2, snapshot balance).
3.  Repayment exceeding current balance rejected (400 Bad Request).
4.  Idempotency exact replay returns 200 OK and does not mutate balance.
5.  Idempotency conflicting payload amount returns 409 Conflict.
6.  Idempotency conflicting payload note returns 409 Conflict.
7.  Idempotency conflicting payload customer returns 409 Conflict.
8.  CREDIT_REVERSAL success and balance update.
9.  REPAYMENT_REVERSAL success and balance update.
10. Credit reversal exceeding current outstanding balance rejected (400 Bad Request).
11. Inactive customer membership rejected (400 Bad Request).
12. Non-shopkeeper authorization rejected (403 Forbidden).
13. Out-of-order transaction start follows serialized commitment order.
14. Concurrent repayment and credit reversal deadlock-free execution.
15. Deadlock retry handler (40P01) simulation with exponential backoff and recovery.
16. Customer history pagination (sequence_number DESC) and global ledger summary.
17. Audit window function verification: running sum equals snapshot balance for all entries.
18. Concurrent identical requests: one creates (201), one replays (200).
19. Concurrent conflicting requests: one creates (201), one fails with 409 Conflict.
20. Reversal same key with different original_entry_id returns 409 Conflict.
21. Empty ledger and pagination controls (limit and offset slicing).
22. Cross-customer and cross-shop authorization isolation.
23. Successive partial reversals up to exact limit, with excessive rejected.
24. Membership deactivation during concurrent processing rejected (400 Bad Request).
25. Genuine PostgreSQL deadlock (40P01) cross-row contention and automated retry recovery.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import random
import threading
import uuid
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
import psycopg2
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.models import LedgerEntry, Shop, ShopCustomer, User
from app.services.ledger_service import LedgerService, execute_with_deadlock_retry
from main import app


@pytest.fixture(scope="module")
def disposable_ledger_schema():
    """
    Creates an isolated disposable PostgreSQL schema, runs Alembic migrations up to head
    (a2e5d9f1c74b), creates sync and async engine targeting this schema, and tears it down.
    """
    conn_str = settings.DATABASE_SYNC_URL.replace("postgresql+psycopg2://", "postgresql://")
    schema_id = uuid.uuid4().hex[:8]
    schema_name = f"disp_test_ledger_api_{schema_id}"

    # 1. Create schema
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name};")
    conn.close()

    # 2. Configure Alembic to migrate the disposable schema
    schema_sync_url = f"{settings.DATABASE_SYNC_URL}?options=-csearch_path%3D{schema_name}"
    sync_engine = create_engine(schema_sync_url, pool_pre_ping=True)

    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = str(backend_dir / "alembic.ini")
    script_location = str(backend_dir / "alembic")

    cfg = Config(ini_path)
    cfg.set_main_option("script_location", script_location)
    cfg.set_main_option("sqlalchemy.url", schema_sync_url.replace("%", "%%"))

    command.upgrade(cfg, "a2e5d9f1c74b")

    # 3. Create async engine for test FastAPI runtime
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema_name}},
        poolclass=NullPool,
        future=True,
    )
    AsyncSessionScoped = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    yield {
        "schema_name": schema_name,
        "sync_engine": sync_engine,
        "async_engine": async_engine,
        "session_factory": AsyncSessionScoped,
        "conn_str": conn_str,
    }

    # Teardown
    sync_engine.dispose()
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
    conn.close()


@pytest.fixture(scope="module")
def seeded_users_and_shops(disposable_ledger_schema):
    """
    Seeds shopkeeper, customer 1, customer 2, and intruder user into the disposable schema.
    """
    engine = disposable_ledger_schema["sync_engine"]
    shopkeeper_id = uuid.uuid4()
    customer_1_id = uuid.uuid4()
    customer_2_id = uuid.uuid4()
    customer_3_id = uuid.uuid4()
    intruder_id = uuid.uuid4()

    shop_id = uuid.uuid4()
    shop_2_id = uuid.uuid4()

    with engine.connect() as conn:
        with conn.begin():
            # Seed users
            conn.execute(
                text("""
                INSERT INTO users (id, phone, password_hash, is_active, created_at, updated_at)
                VALUES
                    (:sk_id, '+919999111001', 'hash1', true, NOW(), NOW()),
                    (:c1_id, '+919999111002', 'hash2', true, NOW(), NOW()),
                    (:c2_id, '+919999111003', 'hash3', true, NOW(), NOW()),
                    (:c3_id, '+919999111005', 'hash5', true, NOW(), NOW()),
                    (:int_id, '+919999111004', 'hash4', true, NOW(), NOW())
            """),
                {
                    "sk_id": shopkeeper_id,
                    "c1_id": customer_1_id,
                    "c2_id": customer_2_id,
                    "c3_id": customer_3_id,
                    "int_id": intruder_id,
                },
            )

            # Seed shops
            conn.execute(
                text("""
                INSERT INTO shops (id, owner_user_id, shop_name, shop_address, created_at, updated_at)
                VALUES
                    (:s_id, :sk_id, 'Primary Udhaar Store', 'Main Bazaar Road', NOW(), NOW()),
                    (:s2_id, :sk_id, 'Secondary Branch Store', 'Station Road', NOW(), NOW())
            """),
                {"s_id": shop_id, "s2_id": shop_2_id, "sk_id": shopkeeper_id},
            )

            # Seed ShopCustomer associations:
            # Customer 1 -> Shop 1 (ACTIVE)
            conn.execute(
                text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, current_balance_paise, last_entry_sequence, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s_id, :c1_id, 'ACTIVE', 0, 0, NOW(), NOW(), NOW())
            """),
                {"sc_id": uuid.uuid4(), "s_id": shop_id, "c1_id": customer_1_id},
            )

            # Customer 1 -> Shop 2 (ACTIVE)
            conn.execute(
                text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, current_balance_paise, last_entry_sequence, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s2_id, :c1_id, 'ACTIVE', 0, 0, NOW(), NOW(), NOW())
            """),
                {"sc_id": uuid.uuid4(), "s2_id": shop_2_id, "c1_id": customer_1_id},
            )

            # Customer 2 -> Shop 1 (INACTIVE)
            conn.execute(
                text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, current_balance_paise, last_entry_sequence, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s_id, :c2_id, 'INACTIVE', 0, 0, NOW(), NOW(), NOW())
            """),
                {"sc_id": uuid.uuid4(), "s_id": shop_id, "c2_id": customer_2_id},
            )

            # Customer 3 -> Shop 1 (ACTIVE)
            conn.execute(
                text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, current_balance_paise, last_entry_sequence, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s_id, :c3_id, 'ACTIVE', 0, 0, NOW(), NOW(), NOW())
            """),
                {"sc_id": uuid.uuid4(), "s_id": shop_id, "c3_id": customer_3_id},
            )

    return {
        "shopkeeper_id": shopkeeper_id,
        "customer_1_id": customer_1_id,
        "customer_2_id": customer_2_id,
        "customer_3_id": customer_3_id,
        "intruder_id": intruder_id,
        "shop_id": shop_id,
        "shop_2_id": shop_2_id,
        "shopkeeper_token": create_access_token(data={"sub": str(shopkeeper_id), "phone": "+919999111001", "role": "shopkeeper"}),
        "customer_1_token": create_access_token(data={"sub": str(customer_1_id), "phone": "+919999111002", "role": "customer"}),
        "intruder_token": create_access_token(data={"sub": str(intruder_id), "phone": "+919999111004", "role": "customer"}),
    }


@pytest.fixture
async def ledger_client(disposable_ledger_schema):
    """
    Provides an AsyncClient hooked up to the disposable schema via dependency override.
    """
    session_factory = disposable_ledger_schema["session_factory"]

    async def override_db():
        async with session_factory() as session:
            yield session

    from app.db.session import get_session_factory

    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)


# Shared transaction IDs for chained verification
_created_credit_entry_id = None
_created_repayment_entry_id = None
_first_repayment_idem_key = None


# ==============================================================================
# TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_01_record_credit_success_and_balance_update(ledger_client, seeded_users_and_shops):
    """
    1. Records CREDIT of ₹1,000 (100,000 paise).
       - Returns HTTP 201 Created.
       - sequence_number = 1.
       - balance_after_transaction_paise = 100,000.
       - current_balance_paise = 100,000.
       - is_idempotent_replay = False.
    """
    global _created_credit_entry_id
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "CREDIT",
        "amount_paise": 100000,
        "note": "Initial Groceries Udhaar",
        "idempotency_key": f"idem-cr-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["is_idempotent_replay"] is False
    assert data["current_balance_paise"] == 100000
    entry = data["entry"]
    assert entry["transaction_type"] == "CREDIT"
    assert entry["amount_paise"] == 100000
    assert entry["sequence_number"] == 1
    assert entry["balance_after_transaction_paise"] == 100000
    assert entry["original_entry_id"] is None

    _created_credit_entry_id = uuid.UUID(entry["id"])


@pytest.mark.asyncio
async def test_02_record_repayment_success_and_balance_update(ledger_client, seeded_users_and_shops):
    """
    2. Records REPAYMENT of ₹400 (40,000 paise).
       - Returns HTTP 201 Created.
       - sequence_number = 2.
       - balance_after_transaction_paise = 60,000.
       - current_balance_paise = 60,000.
       - is_idempotent_replay = False.
    """
    global _created_repayment_entry_id, _first_repayment_idem_key
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]
    _first_repayment_idem_key = f"idem-rp-{uuid.uuid4()}"

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT",
        "amount_paise": 40000,
        "note": "Partial repayment ₹400",
        "idempotency_key": _first_repayment_idem_key,
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["is_idempotent_replay"] is False
    assert data["current_balance_paise"] == 60000
    entry = data["entry"]
    assert entry["transaction_type"] == "REPAYMENT"
    assert entry["amount_paise"] == 40000
    assert entry["sequence_number"] == 2
    assert entry["balance_after_transaction_paise"] == 60000

    _created_repayment_entry_id = uuid.UUID(entry["id"])


@pytest.mark.asyncio
async def test_03_repayment_exceeding_current_balance_rejected_400(ledger_client, seeded_users_and_shops):
    """
    3. Outstanding balance is ₹600 (60,000 paise).
       Attempting repayment of ₹600.01 (60,001 paise) must be rejected with HTTP 400.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT",
        "amount_paise": 60001,
        "note": "Excessive repayment attempt",
        "idempotency_key": f"idem-rp-excess-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    assert "exceeds current outstanding balance" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_04_idempotency_exact_replay_returns_200_and_does_not_mutate_balance(ledger_client, seeded_users_and_shops):
    """
    4. Exact payload replay with identical idempotency key:
       - Returns HTTP 200 OK (NOT 201).
       - is_idempotent_replay = True.
       - Returns the existing committed entry.
       - Outstanding balance remains ₹600 (60,000 paise).
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT",
        "amount_paise": 40000,
        "note": "Partial repayment ₹400",
        "idempotency_key": _first_repayment_idem_key,
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["is_idempotent_replay"] is True
    assert data["current_balance_paise"] == 60000
    assert uuid.UUID(data["entry"]["id"]) == _created_repayment_entry_id
    assert data["entry"]["sequence_number"] == 2


@pytest.mark.asyncio
async def test_05_idempotency_conflicting_payload_amount_returns_409(ledger_client, seeded_users_and_shops):
    """5. Same idempotency key with conflicting amount_paise returns HTTP 409 Conflict."""
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT",
        "amount_paise": 50000,  # Changed from 40000
        "note": "Partial repayment ₹400",
        "idempotency_key": _first_repayment_idem_key,
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409, res.text
    assert "different payload" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_06_idempotency_conflicting_payload_note_returns_409(ledger_client, seeded_users_and_shops):
    """6. Same idempotency key with conflicting note returns HTTP 409 Conflict."""
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT",
        "amount_paise": 40000,
        "note": "Completely altered description",  # Changed note
        "idempotency_key": _first_repayment_idem_key,
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409, res.text
    assert "different payload" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_07_idempotency_conflicting_payload_customer_returns_409(ledger_client, seeded_users_and_shops):
    """7. Same idempotency key targeting a different customer returns HTTP 409 Conflict."""
    shop_id = seeded_users_and_shops["shop_id"]
    c3_id = seeded_users_and_shops["customer_3_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c3_id),  # Different customer (customer 3, who is ACTIVE)
        "transaction_type": "REPAYMENT",
        "amount_paise": 40000,
        "note": "Partial repayment ₹400",
        "idempotency_key": _first_repayment_idem_key,
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 409, res.text
    assert "different payload" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_08_credit_reversal_success_and_balance_update(ledger_client, seeded_users_and_shops):
    """
    8. Records CREDIT_REVERSAL of ₹200 (20,000 paise) against original credit.
       - Returns HTTP 201 Created.
       - sequence_number = 3.
       - balance_after_transaction_paise = 40,000 (60,000 - 20,000).
       - current_balance_paise = 40,000.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "CREDIT_REVERSAL",
        "original_entry_id": str(_created_credit_entry_id),
        "amount_paise": 20000,
        "note": "Item returned by customer",
        "idempotency_key": f"idem-rev-cr-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["current_balance_paise"] == 40000
    entry = data["entry"]
    assert entry["transaction_type"] == "CREDIT_REVERSAL"
    assert entry["sequence_number"] == 3
    assert entry["balance_after_transaction_paise"] == 40000
    assert uuid.UUID(entry["original_entry_id"]) == _created_credit_entry_id


@pytest.mark.asyncio
async def test_09_repayment_reversal_success_and_balance_update(ledger_client, seeded_users_and_shops):
    """
    9. Records REPAYMENT_REVERSAL of ₹100 (10,000 paise) against original repayment.
       - Returns HTTP 201 Created.
       - sequence_number = 4.
       - balance_after_transaction_paise = 50,000 (40,000 + 10,000).
       - current_balance_paise = 50,000.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "REPAYMENT_REVERSAL",
        "original_entry_id": str(_created_repayment_entry_id),
        "amount_paise": 10000,
        "note": "Cheque bounced / reversed",
        "idempotency_key": f"idem-rev-rp-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["current_balance_paise"] == 50000
    entry = data["entry"]
    assert entry["transaction_type"] == "REPAYMENT_REVERSAL"
    assert entry["sequence_number"] == 4
    assert entry["balance_after_transaction_paise"] == 50000
    assert uuid.UUID(entry["original_entry_id"]) == _created_repayment_entry_id


@pytest.mark.asyncio
async def test_10_credit_reversal_exceeding_outstanding_balance_rejected_400(
    ledger_client, seeded_users_and_shops, disposable_ledger_schema
):
    """
    10. Requirement 5 verification:
        When customer has repaid part of credit and outstanding balance is less than
        the requested credit reversal, the request MUST be rejected with HTTP 400.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    token = seeded_users_and_shops["shopkeeper_token"]
    sync_engine = disposable_ledger_schema["sync_engine"]

    # Create isolated customer user
    isolated_customer_id = uuid.uuid4()
    credit_entry_id = uuid.uuid4()

    with sync_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text("""
                INSERT INTO users (id, phone, password_hash, is_active, created_at, updated_at)
                VALUES (:cid, '+919999222333', 'hash', true, NOW(), NOW())
            """),
                {"cid": isolated_customer_id},
            )
            # Balance = 20,000 paise (₹200)
            conn.execute(
                text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, current_balance_paise, last_entry_sequence, joined_at, created_at, updated_at)
                VALUES (:scid, :sid, :cid, 'ACTIVE', 20000, 2, NOW(), NOW(), NOW())
            """),
                {"scid": uuid.uuid4(), "sid": shop_id, "cid": isolated_customer_id},
            )
            # Original credit = 100,000 paise (₹1,000)
            conn.execute(
                text("""
                INSERT INTO ledger_entries (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES (:eid, :sid, :cid, :byid, 'CREDIT', 100000, 'Original credit ₹1000', :idem, 1, 100000, NOW())
            """),
                {
                    "eid": credit_entry_id,
                    "sid": shop_id,
                    "cid": isolated_customer_id,
                    "byid": seeded_users_and_shops["shopkeeper_id"],
                    "idem": f"idem-iso-cr-{uuid.uuid4()}",
                },
            )

    # Attempt CREDIT_REVERSAL of 100,000 against balance of 20,000
    payload = {
        "customer_user_id": str(isolated_customer_id),
        "transaction_type": "CREDIT_REVERSAL",
        "original_entry_id": str(credit_entry_id),
        "amount_paise": 100000,
        "note": "Attempt reversal exceeding balance",
        "idempotency_key": f"idem-iso-rev-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    detail = res.json()["detail"].lower()
    assert "exceeds current customer balance" in detail
    assert "already repaid" in detail


@pytest.mark.asyncio
async def test_11_inactive_customer_relationship_rejected_400(ledger_client, seeded_users_and_shops):
    """11. Attempting ledger entry for INACTIVE customer (customer 2) returns HTTP 400."""
    shop_id = seeded_users_and_shops["shop_id"]
    c2_id = seeded_users_and_shops["customer_2_id"]  # INACTIVE in setup
    token = seeded_users_and_shops["shopkeeper_token"]

    payload = {
        "customer_user_id": str(c2_id),
        "transaction_type": "CREDIT",
        "amount_paise": 50000,
        "note": "Credit for inactive member",
        "idempotency_key": f"idem-inact-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    assert "not active" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_12_non_shopkeeper_unauthorized_403(ledger_client, seeded_users_and_shops):
    """12. A non-owner user attempting to create a ledger entry returns HTTP 403 Forbidden."""
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    intruder_token = seeded_users_and_shops["intruder_token"]

    payload = {
        "customer_user_id": str(c1_id),
        "transaction_type": "CREDIT",
        "amount_paise": 15000,
        "note": "Unauthorized ledger insert",
        "idempotency_key": f"idem-unauth-{uuid.uuid4()}",
    }

    res = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json=payload,
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert res.status_code == 403, res.text
    assert "only the shop owner" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_13_out_of_order_transaction_start_follows_serialization_order(
    disposable_ledger_schema, seeded_users_and_shops
):
    """
    13. Critical Historical Ordering Test:
        Proves that a transaction starting earlier but committing later
        receives a sequence number reflecting its actual commitment order.
        Worker 1 (Repayment ₹400) begins first at T=0.
        Worker 2 (Credit ₹1,000) begins second, acquires lock first, commits.
        Worker 1 acquires lock second, commits.
        Result: Credit receives sequence 1 (₹1,000), Repayment receives sequence 2 (₹600).
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]
    sk_id = seeded_users_and_shops["shopkeeper_id"]

    # Create fresh isolated customer
    test_cust_id = uuid.uuid4()
    async with session_factory() as s:
        new_cust = User(
            id=test_cust_id,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        )
        s.add(new_cust)
        new_link = ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=test_cust_id,
            status="ACTIVE",
            current_balance_paise=0,
            last_entry_sequence=0,
        )
        s.add(new_link)
        await s.commit()

    barrier_start = asyncio.Barrier(2)
    worker2_committed = asyncio.Event()

    results = {}

    async def worker_1():
        # Starts first, but yields lock until worker 2 commits
        async with session_factory() as s:
            await barrier_start.wait()
            # Wait for worker 2 to acquire the lock and commit
            await worker2_committed.wait()

            # Now worker 1 executes Repayment of ₹400
            from app.schemas.ledger import CreateLedgerEntryRequest

            req = CreateLedgerEntryRequest(
                customer_user_id=test_cust_id,
                transaction_type="REPAYMENT",
                amount_paise=40000,
                idempotency_key=f"idem-ord-w1-{uuid.uuid4()}",
            )
            entry, bal, _ = await LedgerService.record_transaction(
                s, shop_id, test_cust_id, sk_id, req
            )
            results["worker_1"] = (entry.sequence_number, entry.balance_after_transaction_paise)

    async def worker_2():
        async with session_factory() as s:
            await barrier_start.wait()
            # Worker 2 records Credit of ₹1,000 immediately
            from app.schemas.ledger import CreateLedgerEntryRequest

            req = CreateLedgerEntryRequest(
                customer_user_id=test_cust_id,
                transaction_type="CREDIT",
                amount_paise=100000,
                idempotency_key=f"idem-ord-w2-{uuid.uuid4()}",
            )
            entry, bal, _ = await LedgerService.record_transaction(
                s, shop_id, test_cust_id, sk_id, req
            )
            results["worker_2"] = (entry.sequence_number, entry.balance_after_transaction_paise)
            # Signal worker 1
            worker2_committed.set()

    await asyncio.gather(worker_1(), worker_2())

    # Assert Worker 2 (Credit) got sequence 1 and balance 100,000
    assert results["worker_2"] == (1, 100000)
    # Assert Worker 1 (Repayment) got sequence 2 and balance 60,000
    assert results["worker_1"] == (2, 60000)


@pytest.mark.asyncio
async def test_14_concurrent_repayment_and_credit_reversal_deadlock_free(
    disposable_ledger_schema, seeded_users_and_shops
):
    """
    14. Deadlock-free concurrency test:
        Simultaneous repayment and credit reversal against the same customer account.
        Global lock order (ShopCustomer first, original LedgerEntry second) guarantees
        deadlock freedom.
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]
    sk_id = seeded_users_and_shops["shopkeeper_id"]

    # Create fresh customer with ₹500 credit
    test_cust_id = uuid.uuid4()
    orig_credit_id = uuid.uuid4()

    async with session_factory() as s:
        new_cust = User(
            id=test_cust_id,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        )
        s.add(new_cust)
        new_link = ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=test_cust_id,
            status="ACTIVE",
            current_balance_paise=50000,
            last_entry_sequence=1,
        )
        s.add(new_link)
        orig_credit = LedgerEntry(
            id=orig_credit_id,
            shop_id=shop_id,
            customer_user_id=test_cust_id,
            created_by_user_id=sk_id,
            transaction_type="CREDIT",
            amount_paise=50000,
            idempotency_key=f"idem-orig-conc-{uuid.uuid4()}",
            sequence_number=1,
            balance_after_transaction_paise=50000,
            created_at=datetime.now(timezone.utc),
        )
        s.add(orig_credit)
        await s.commit()

    barrier = asyncio.Barrier(2)

    async def op_repayment():
        await barrier.wait()
        from app.schemas.ledger import CreateLedgerEntryRequest

        req = CreateLedgerEntryRequest(
            customer_user_id=test_cust_id,
            transaction_type="REPAYMENT",
            amount_paise=15000,
            idempotency_key=f"idem-conc-rp-{uuid.uuid4()}",
        )
        return await LedgerService.record_transaction_with_retry(
            shop_id, test_cust_id, sk_id, req, session_factory
        )

    async def op_reversal():
        await barrier.wait()
        from app.schemas.ledger import CreateReversalRequest

        req = CreateReversalRequest(
            customer_user_id=test_cust_id,
            transaction_type="CREDIT_REVERSAL",
            original_entry_id=orig_credit_id,
            amount_paise=20000,
            idempotency_key=f"idem-conc-rev-{uuid.uuid4()}",
        )
        return await LedgerService.record_reversal_with_retry(
            shop_id, test_cust_id, sk_id, req, session_factory
        )

    res_rp, res_rev = await asyncio.gather(op_repayment(), op_reversal())

    # Both must succeed without deadlock
    assert res_rp[0] is not None
    assert res_rev[0] is not None

    # Final balance must be 50,000 - 15,000 - 20,000 = 15,000 paise
    async with session_factory() as s:
        final_sc = (
            await s.execute(
                text("SELECT current_balance_paise, last_entry_sequence FROM shop_customers WHERE customer_user_id = :cid"),
                {"cid": test_cust_id},
            )
        ).fetchone()
        assert final_sc[0] == 15000
        assert final_sc[1] == 3


@pytest.mark.asyncio
async def test_15_deadlock_retry_handler(disposable_ledger_schema):
    """
    15. Tests execute_with_deadlock_retry:
        Simulates a PostgreSQL 40P01 DeadlockDetected error on the first attempt.
        Verifies that the retry handler catches 40P01, applies backoff, and succeeds on attempt 2.
    """
    session_factory = disposable_ledger_schema["session_factory"]

    call_count = 0

    class FakePgError(Exception):
        pgcode = "40P01"

    class FakeDBAPIError(DBAPIError):
        def __init__(self):
            super().__init__("deadlock detected", None, FakePgError())

    async def flaky_operation(session):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FakeDBAPIError()
        return "SUCCESS_ON_RETRY"

    result = await execute_with_deadlock_retry(session_factory, flaky_operation)
    assert result == "SUCCESS_ON_RETRY"
    assert call_count == 2, f"Expected 2 attempts (1 failure + 1 retry), got {call_count}"


@pytest.mark.asyncio
async def test_16_customer_history_and_global_summary(ledger_client, seeded_users_and_shops):
    """
    16. Verifies customer history ordering (sequence_number DESC)
        and global summary across multiple shops.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_token = seeded_users_and_shops["customer_1_token"]

    # Customer queries history at primary shop
    res_hist = await ledger_client.get(
        f"/api/v1/customer/shops/{shop_id}/ledger",
        headers={"Authorization": f"Bearer {c1_token}"},
    )
    assert res_hist.status_code == 200, res_hist.text
    hist_data = res_hist.json()

    assert hist_data["total_count"] == 4
    items = hist_data["items"]
    # Verify strict descending order: 4, 3, 2, 1
    sequences = [item["sequence_number"] for item in items]
    assert sequences == [4, 3, 2, 1], f"Expected sequence [4, 3, 2, 1], got {sequences}"

    # Customer queries global summary across all joined shops
    res_sum = await ledger_client.get(
        "/api/v1/customer/ledger/summary",
        headers={"Authorization": f"Bearer {c1_token}"},
    )
    assert res_sum.status_code == 200, res_sum.text
    sum_data = res_sum.json()

    assert sum_data["total_outstanding_paise"] == 50000
    assert len(sum_data["shops"]) >= 1
    primary_shop = next(s for s in sum_data["shops"] if uuid.UUID(s["shop_id"]) == shop_id)
    assert primary_shop["current_balance_paise"] == 50000
    assert primary_shop["last_entry_sequence"] == 4


@pytest.mark.asyncio
async def test_17_audit_running_balance_window_function_matches_snapshots(
    disposable_ledger_schema, seeded_users_and_shops
):
    """
    17. Mathematical & Historical Balance Audit:
        Runs PostgreSQL window function over all entries for Customer 1:
        SUM(delta) OVER (PARTITION BY shop_id, customer_user_id ORDER BY sequence_number ASC)
        Verifies that every historical snapshot balance_after_transaction_paise
        strictly equals the window function running sum.
    """
    sync_engine = disposable_ledger_schema["sync_engine"]
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]

    with sync_engine.connect() as conn:
        rows = conn.execute(
            text("""
            SELECT
                sequence_number,
                transaction_type,
                amount_paise,
                balance_after_transaction_paise,
                SUM(
                    CASE
                        WHEN transaction_type IN ('CREDIT', 'REPAYMENT_REVERSAL') THEN amount_paise
                        WHEN transaction_type IN ('REPAYMENT', 'CREDIT_REVERSAL') THEN -amount_paise
                        ELSE 0
                    END
                ) OVER (
                    PARTITION BY shop_id, customer_user_id
                    ORDER BY sequence_number ASC
                ) AS calculated_running_balance
            FROM ledger_entries
            WHERE shop_id = :sid AND customer_user_id = :cid
            ORDER BY sequence_number ASC;
        """),
            {"sid": shop_id, "cid": c1_id},
        ).fetchall()

        assert len(rows) == 4, f"Expected 4 entries for customer 1, got {len(rows)}"

        for row in rows:
            seq = row[0]
            tx_type = row[1]
            amt = row[2]
            snapshot = row[3]
            calculated = row[4]
            assert snapshot == calculated, (
                f"Audit failed at sequence {seq} ({tx_type} {amt}): "
                f"snapshot balance {snapshot} != calculated running balance {calculated}"
            )


@pytest.mark.asyncio
async def test_18_concurrent_identical_requests_one_creates_one_replays(
    ledger_client, seeded_users_and_shops
):
    """
    18. Two concurrent requests with exact same idempotency key and canonical payload:
        Exactly one request creates the new entry (HTTP 201, is_idempotent_replay: False).
        The other request safely handles the unique constraint race and replays (HTTP 200, is_idempotent_replay: True).
        Total created entries in database is exactly 1.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c3_id = seeded_users_and_shops["customer_3_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    shared_idem = f"idem-race-{uuid.uuid4()}"
    barrier = asyncio.Barrier(2)

    async def submit():
        await barrier.wait()
        return await ledger_client.post(
            f"/api/v1/shops/{shop_id}/ledger/entries",
            json={
                "customer_user_id": str(c3_id),
                "transaction_type": "CREDIT",
                "amount_paise": 25000,
                "note": "Concurrent race test",
                "idempotency_key": shared_idem,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    res1, res2 = await asyncio.gather(submit(), submit())

    codes = sorted([res1.status_code, res2.status_code])
    assert codes == [200, 201], f"Expected one 200 and one 201, got {codes}: {res1.text}, {res2.text}"

    data1 = res1.json()
    data2 = res2.json()

    # Verify both returned the SAME entry ID
    assert data1["entry"]["id"] == data2["entry"]["id"]

    # One was replay, one was new
    replays = [data1["is_idempotent_replay"], data2["is_idempotent_replay"]]
    assert sorted(replays) == [False, True]


@pytest.mark.asyncio
async def test_19_concurrent_conflicting_payloads_same_key(
    ledger_client, seeded_users_and_shops
):
    """
    19. Two concurrent requests with same idempotency key but conflicting payloads:
        - Request A: amount_paise = 15000, note = "Payload A"
        - Request B: amount_paise = 25000, note = "Payload B"
        Exactly one request creates the new entry (HTTP 201).
        The losing request retrieves the committed entry, detects a payload mismatch, and returns HTTP 409 Conflict.
        Total entries created in database is exactly 1.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c3_id = seeded_users_and_shops["customer_3_id"]
    token = seeded_users_and_shops["shopkeeper_token"]
    shared_idem = f"idem-conflict-race-{uuid.uuid4()}"
    barrier = asyncio.Barrier(2)

    async def submit(amount: int, note: str):
        await barrier.wait()
        return await ledger_client.post(
            f"/api/v1/shops/{shop_id}/ledger/entries",
            json={
                "customer_user_id": str(c3_id),
                "transaction_type": "CREDIT",
                "amount_paise": amount,
                "note": note,
                "idempotency_key": shared_idem,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    res1, res2 = await asyncio.gather(
        submit(15000, "Payload A"),
        submit(25000, "Payload B"),
    )

    statuses = sorted([res1.status_code, res2.status_code])
    assert statuses == [201, 409], f"Expected [201, 409], got {statuses}: {res1.text}, {res2.text}"

    err_res = res1 if res1.status_code == 409 else res2
    assert "already used with a different payload" in err_res.json()["detail"]


@pytest.mark.asyncio
async def test_20_reversal_same_key_different_original_entry_id_returns_409(
    ledger_client, seeded_users_and_shops
):
    """
    20. Submits a reversal with an idempotency key, then replays the same key
        with a different original_entry_id:
        - First reversal succeeds with HTTP 201 Created.
        - Second reversal with altered original_entry_id returns HTTP 409 Conflict.
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c3_id = seeded_users_and_shops["customer_3_id"]
    token = seeded_users_and_shops["shopkeeper_token"]

    # Create two distinct credit entries
    res_c1 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json={
            "customer_user_id": str(c3_id),
            "transaction_type": "CREDIT",
            "amount_paise": 20000,
            "note": "Credit 1 for reversal test",
            "idempotency_key": f"idem-c1-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_c1.status_code == 201
    entry_id_1 = res_c1.json()["entry"]["id"]

    res_c2 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json={
            "customer_user_id": str(c3_id),
            "transaction_type": "CREDIT",
            "amount_paise": 20000,
            "note": "Credit 2 for reversal test",
            "idempotency_key": f"idem-c2-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_c2.status_code == 201
    entry_id_2 = res_c2.json()["entry"]["id"]

    # Reversal 1 referencing entry_id_1
    reversal_idem = f"idem-rev-mismatch-{uuid.uuid4()}"
    res_rev1 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(c3_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": entry_id_1,
            "amount_paise": 10000,
            "note": "Reversal targeting entry 1",
            "idempotency_key": reversal_idem,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_rev1.status_code == 201, res_rev1.text

    # Reversal 2 using SAME idempotency key but referencing entry_id_2
    res_rev2 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(c3_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": entry_id_2,
            "amount_paise": 10000,
            "note": "Reversal targeting entry 1",
            "idempotency_key": reversal_idem,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_rev2.status_code == 409, res_rev2.text
    assert "already used with a different payload" in res_rev2.json()["detail"]


@pytest.mark.asyncio
async def test_21_empty_ledger_and_pagination(
    disposable_ledger_schema, ledger_client, seeded_users_and_shops
):
    """
    21. Verifies empty ledger responses and pagination controls (limit and offset):
        - Customer with 0 transactions returns total_count=0 and items=[].
        - Multi-transaction customer: limit and offset correctly slice descending sequences.
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]
    sk_token = seeded_users_and_shops["shopkeeper_token"]
    c1_id = seeded_users_and_shops["customer_1_id"]

    # 1. Create a customer with 0 transactions
    fresh_cust_id = uuid.uuid4()
    async with session_factory() as s:
        new_cust = User(
            id=fresh_cust_id,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        )
        s.add(new_cust)
        sc = ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=fresh_cust_id,
            status="ACTIVE",
            current_balance_paise=0,
            last_entry_sequence=0,
        )
        s.add(sc)
        await s.commit()

    fresh_cust_token = create_access_token(
        data={"sub": str(fresh_cust_id), "phone": "+919999000099", "role": "customer"}
    )

    # Empty ledger from customer view
    res_cust_empty = await ledger_client.get(
        f"/api/v1/customer/shops/{shop_id}/ledger",
        headers={"Authorization": f"Bearer {fresh_cust_token}"},
    )
    assert res_cust_empty.status_code == 200
    empty_cust_data = res_cust_empty.json()
    assert empty_cust_data["total_count"] == 0
    assert empty_cust_data["items"] == []
    assert empty_cust_data["current_balance_paise"] == 0
    assert empty_cust_data["last_entry_sequence"] == 0

    # Empty ledger from shopkeeper view
    res_sk_empty = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{fresh_cust_id}",
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_sk_empty.status_code == 200
    empty_sk_data = res_sk_empty.json()
    assert empty_sk_data["total_count"] == 0
    assert empty_sk_data["items"] == []
    assert empty_sk_data["current_balance_paise"] == 0
    assert empty_sk_data["last_entry_sequence"] == 0

    # 2. Pagination on Customer 1 (which has 4 transactions: seq 4, 3, 2, 1)
    # Page 1: limit=2, offset=0 -> sequences [4, 3]
    res_p1 = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{c1_id}?limit=2&offset=0",
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["total_count"] == 4
    assert len(p1_data["items"]) == 2
    assert [x["sequence_number"] for x in p1_data["items"]] == [4, 3]

    # Page 2: limit=2, offset=2 -> sequences [2, 1]
    res_p2 = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{c1_id}?limit=2&offset=2",
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_p2.status_code == 200
    p2_data = res_p2.json()
    assert p2_data["total_count"] == 4
    assert len(p2_data["items"]) == 2
    assert [x["sequence_number"] for x in p2_data["items"]] == [2, 1]

    # Page 3: limit=2, offset=4 -> []
    res_p3 = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{c1_id}?limit=2&offset=4",
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_p3.status_code == 200
    p3_data = res_p3.json()
    assert p3_data["total_count"] == 4
    assert len(p3_data["items"]) == 0


@pytest.mark.asyncio
async def test_22_cross_customer_and_cross_shop_authorization_isolation(
    ledger_client, seeded_users_and_shops
):
    """
    22. Verifies authorization boundaries:
        - Non-owner shopkeeper cannot record transactions or view ledger for another shop (403 Forbidden).
        - Customer cannot access shopkeeper management endpoints (403 Forbidden).
        - Customer cannot read another customer's ledger records (customer endpoints only serve own records).
    """
    shop_id = seeded_users_and_shops["shop_id"]
    c1_id = seeded_users_and_shops["customer_1_id"]
    c1_token = seeded_users_and_shops["customer_1_token"]
    intruder_token = seeded_users_and_shops["intruder_token"]

    # 1. Intruder attempts to record transaction for shop_id -> 403 Forbidden
    res_int_post = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json={
            "customer_user_id": str(c1_id),
            "transaction_type": "CREDIT",
            "amount_paise": 1000,
            "idempotency_key": f"idem-unauth-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert res_int_post.status_code == 403, res_int_post.text
    assert "Only the shop owner" in res_int_post.json()["detail"]

    # 2. Intruder attempts to view customer 1's ledger via shopkeeper endpoint -> 403 Forbidden
    res_int_get = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{c1_id}",
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert res_int_get.status_code == 403, res_int_get.text
    assert "Only the shop owner" in res_int_get.json()["detail"]

    # 3. Customer 1 attempts to call shopkeeper endpoint -> 403 Forbidden
    res_c1_sk_ep = await ledger_client.get(
        f"/api/v1/shops/{shop_id}/ledger/customers/{c1_id}",
        headers={"Authorization": f"Bearer {c1_token}"},
    )
    assert res_c1_sk_ep.status_code == 403

    # 4. Intruder queries customer ledger endpoint for shop_id (where intruder is not joined) -> 404 Not Found
    res_int_cust_ep = await ledger_client.get(
        f"/api/v1/customer/shops/{shop_id}/ledger",
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert res_int_cust_ep.status_code == 404
    assert "Customer has not joined this shop" in res_int_cust_ep.json()["detail"]


@pytest.mark.asyncio
async def test_23_successive_partial_reversals(
    disposable_ledger_schema, ledger_client, seeded_users_and_shops
):
    """
    23. Successive Partial Reversals:
        - Original CREDIT: ₹1,000 (100,000 paise).
        - Reversal 1: ₹300 (30,000 paise) -> Success (201), balance = 70,000 paise.
        - Reversal 2: ₹400 (40,000 paise) -> Success (201), balance = 30,000 paise.
        - Reversal 3 (excessive): ₹400 (40,000 paise) -> Rejected (400), exceeds remaining 30,000 paise.
        - Reversal 4 (exact remaining): ₹300 (30,000 paise) -> Success (201), balance = 0 paise.
        - Reversal 5 (any additional): ₹100 (10,000 paise) -> Rejected (400), original entry fully reversed.
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]
    sk_token = seeded_users_and_shops["shopkeeper_token"]

    cust_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(User(
            id=cust_id,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        ))
        s.add(ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=cust_id,
            status="ACTIVE",
            current_balance_paise=0,
            last_entry_sequence=0,
        ))
        await s.commit()

    # Step 1: Create initial CREDIT of 100,000 paise
    res_orig = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/entries",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT",
            "amount_paise": 100000,
            "note": "Initial ₹1,000 credit for partial reversals",
            "idempotency_key": f"idem-orig-part-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_orig.status_code == 201
    orig_entry_id = res_orig.json()["entry"]["id"]
    assert res_orig.json()["current_balance_paise"] == 100000

    # Step 2: Partial Reversal 1 (30,000 paise)
    res_rev1 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": orig_entry_id,
            "amount_paise": 30000,
            "note": "Partial reversal 1 (₹300)",
            "idempotency_key": f"idem-rev1-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_rev1.status_code == 201
    assert res_rev1.json()["current_balance_paise"] == 70000

    # Step 3: Partial Reversal 2 (40,000 paise)
    res_rev2 = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": orig_entry_id,
            "amount_paise": 40000,
            "note": "Partial reversal 2 (₹400)",
            "idempotency_key": f"idem-rev2-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_rev2.status_code == 201
    assert res_rev2.json()["current_balance_paise"] == 30000

    # Step 4: Excessive Reversal (40,000 paise) -> Must fail
    res_rev3_fail = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": orig_entry_id,
            "amount_paise": 40000,
            "note": "Excessive reversal (₹400, exceeds remaining ₹300)",
            "idempotency_key": f"idem-rev3-fail-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_rev3_fail.status_code == 400
    # Balance must remain untouched at 30,000 paise
    async with session_factory() as s:
        bal = (await s.execute(
            text("SELECT current_balance_paise FROM shop_customers WHERE customer_user_id = :cid"),
            {"cid": cust_id},
        )).scalar()
        assert bal == 30000

    # Step 5: Exact remaining Reversal (30,000 paise) -> Must succeed
    res_rev3_ok = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": orig_entry_id,
            "amount_paise": 30000,
            "note": "Exact remaining reversal (₹300)",
            "idempotency_key": f"idem-rev3-ok-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_rev3_ok.status_code == 201
    assert res_rev3_ok.json()["current_balance_paise"] == 0

    # Step 6: Any further reversal rejected (entry fully reversed)
    res_rev4_fail = await ledger_client.post(
        f"/api/v1/shops/{shop_id}/ledger/reversals",
        json={
            "customer_user_id": str(cust_id),
            "transaction_type": "CREDIT_REVERSAL",
            "original_entry_id": orig_entry_id,
            "amount_paise": 1000,
            "note": "Further reversal after 100% reversed",
            "idempotency_key": f"idem-rev4-fail-{uuid.uuid4()}",
        },
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert res_rev4_fail.status_code == 400


@pytest.mark.asyncio
async def test_24_membership_deactivation_during_concurrent_processing(
    disposable_ledger_schema, seeded_users_and_shops
):
    """
    24. Verifies that when a customer's membership is deactivated while a transaction
        is queued/waiting for the ShopCustomer lock, the transaction immediately detects
        the INACTIVE status once it acquires the row lock and fails with HTTP 400 Bad Request.
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]
    sk_id = seeded_users_and_shops["shopkeeper_id"]

    cust_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(User(
            id=cust_id,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        ))
        s.add(ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=cust_id,
            status="ACTIVE",
            current_balance_paise=10000,
            last_entry_sequence=1,
        ))
        await s.commit()

    barrier = asyncio.Barrier(2)

    async def deactivator():
        async with session_factory() as s:
            await s.execute(
                text("SELECT id FROM shop_customers WHERE customer_user_id = :cid FOR UPDATE"),
                {"cid": cust_id},
            )
            await barrier.wait()
            await asyncio.sleep(0.05)
            await s.execute(
                text("UPDATE shop_customers SET status = 'INACTIVE' WHERE customer_user_id = :cid"),
                {"cid": cust_id},
            )
            await s.commit()

    async def queued_tx():
        await barrier.wait()
        await asyncio.sleep(0.01)

        from app.schemas.ledger import CreateLedgerEntryRequest
        req = CreateLedgerEntryRequest(
            customer_user_id=cust_id,
            transaction_type="CREDIT",
            amount_paise=5000,
            idempotency_key=f"idem-deact-{uuid.uuid4()}",
        )
        try:
            await LedgerService.record_transaction_with_retry(
                shop_id, cust_id, sk_id, req, session_factory
            )
            return "SUCCESS"
        except HTTPException as e:
            return e

    res_deact, res_tx = await asyncio.gather(deactivator(), queued_tx())

    assert isinstance(res_tx, HTTPException)
    assert res_tx.status_code == 400
    assert "Customer membership is not ACTIVE" in res_tx.detail


@pytest.mark.asyncio
async def test_25_actual_postgresql_deadlock_recovery_integration(
    disposable_ledger_schema, seeded_users_and_shops
):
    """
    25. Genuine PostgreSQL Deadlock Detection and Retry Integration Test:
        - Two concurrent transactions acquire locks on two ShopCustomer rows in opposite order:
          Tx A: Locks Cust A -> attempts to lock Cust B
          Tx B: Locks Cust B -> attempts to lock Cust A
        - PostgreSQL deadlock detector fires after deadlock_timeout (1s) and cancels one transaction
          with SQLSTATE 40P01 (deadlock_detected).
        - execute_with_deadlock_retry catches the 40P01 DBAPIError, performs exponential
          backoff with jitter, retries in a fresh session, and successfully commits both!
    """
    session_factory = disposable_ledger_schema["session_factory"]
    shop_id = seeded_users_and_shops["shop_id"]

    cust_a = uuid.uuid4()
    cust_b = uuid.uuid4()
    async with session_factory() as s:
        s.add(User(
            id=cust_a,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        ))
        s.add(User(
            id=cust_b,
            phone=f"+919999{random.randint(100000, 999999)}",
            password_hash="hash",
            is_active=True,
        ))
        s.add(ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=cust_a,
            status="ACTIVE",
            current_balance_paise=0,
            last_entry_sequence=0,
        ))
        s.add(ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop_id,
            customer_user_id=cust_b,
            status="ACTIVE",
            current_balance_paise=0,
            last_entry_sequence=0,
        ))
        await s.commit()

    barrier = asyncio.Barrier(2)
    deadlock_witnessed = []
    has_synced_a = False
    has_synced_b = False

    async def tx_a_work(session):
        nonlocal has_synced_a
        await session.execute(
            text("SELECT id FROM shop_customers WHERE customer_user_id = :cid FOR UPDATE"),
            {"cid": cust_a},
        )
        if not has_synced_a:
            has_synced_a = True
            await barrier.wait()
            await asyncio.sleep(0.02)
        try:
            await session.execute(
                text("SELECT id FROM shop_customers WHERE customer_user_id = :cid FOR UPDATE"),
                {"cid": cust_b},
            )
        except DBAPIError as e:
            orig = getattr(e, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if "deadlock detected" in str(e).lower() or sqlstate == "40P01":
                deadlock_witnessed.append("tx_a")
            raise
        await session.execute(
            text("UPDATE shop_customers SET current_balance_paise = current_balance_paise + 100 WHERE customer_user_id = :cid"),
            {"cid": cust_a},
        )
        await session.commit()
        return "TX_A_DONE"

    async def tx_b_work(session):
        nonlocal has_synced_b
        await session.execute(
            text("SELECT id FROM shop_customers WHERE customer_user_id = :cid FOR UPDATE"),
            {"cid": cust_b},
        )
        if not has_synced_b:
            has_synced_b = True
            await barrier.wait()
            await asyncio.sleep(0.02)
        try:
            await session.execute(
                text("SELECT id FROM shop_customers WHERE customer_user_id = :cid FOR UPDATE"),
                {"cid": cust_a},
            )
        except DBAPIError as e:
            orig = getattr(e, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if "deadlock detected" in str(e).lower() or sqlstate == "40P01":
                deadlock_witnessed.append("tx_b")
            raise
        await session.execute(
            text("UPDATE shop_customers SET current_balance_paise = current_balance_paise + 200 WHERE customer_user_id = :cid"),
            {"cid": cust_b},
        )
        await session.commit()
        return "TX_B_DONE"

    res_a, res_b = await asyncio.gather(
        execute_with_deadlock_retry(session_factory, tx_a_work),
        execute_with_deadlock_retry(session_factory, tx_b_work),
    )

    assert res_a == "TX_A_DONE"
    assert res_b == "TX_B_DONE"
    assert len(deadlock_witnessed) >= 1, f"Expected at least one real 40P01 deadlock, witnessed: {deadlock_witnessed}"

    # Verify both updates succeeded and committed
    async with session_factory() as s:
        bal_a = (await s.execute(
            text("SELECT current_balance_paise FROM shop_customers WHERE customer_user_id = :cid"),
            {"cid": cust_a},
        )).scalar()
        bal_b = (await s.execute(
            text("SELECT current_balance_paise FROM shop_customers WHERE customer_user_id = :cid"),
            {"cid": cust_b},
        )).scalar()
        assert bal_a == 100
        assert bal_b == 200


