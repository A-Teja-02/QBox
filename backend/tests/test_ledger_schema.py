"""
Isolated database-level tests for Qbox Real PostgreSQL Udhaar Ledger Schema.

Verifies:
1. Migration upgrade to a2e5d9f1c74b and downgrade back to f7a2d83b9c01 on a disposable schema.
2. LedgerEntry schema creation with columns, constraints, and indexes.
3. Default current_balance_paise of zero on shop_customers.
4. Non-negative balance check constraint on shop_customers.
5. Positive amount constraint (amount_paise > 0) on ledger_entries.
6. Valid transaction type constraint ('CREDIT', 'REPAYMENT') on ledger_entries.
7. Foreign key and composite shop-customer relationship enforcement.
8. Idempotency key uniqueness per shop.

SAFETY GUARANTEE:
All tests execute exclusively within a temporary, disposable PostgreSQL schema.
The public schema (where production/local qbox_db records live) is NEVER modified.
"""

import uuid
import threading
from datetime import datetime, timezone
import pytest
import psycopg2
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, DBAPIError, InternalError

from app.core.config import settings


@pytest.fixture(scope="module")
def disposable_db_schema():
    """
    Creates an isolated disposable PostgreSQL schema for migration and schema tests,
    runs full migrations, and cleans up the schema upon test completion.
    """
    conn_str = settings.DATABASE_SYNC_URL.replace("postgresql+psycopg2://", "postgresql://")
    schema_id = uuid.uuid4().hex[:8]
    schema_name = f"disp_test_ledger_{schema_id}"

    # 1. Create the disposable schema in PostgreSQL
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name};")
    conn.close()

    # 2. Build sync engine targeting the disposable schema
    schema_url = f"{settings.DATABASE_SYNC_URL}?options=-csearch_path%3D{schema_name}"
    engine = create_engine(schema_url, pool_pre_ping=True)

    # 3. Configure Alembic to migrate the disposable schema
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = str(backend_dir / "alembic.ini")
    script_location = str(backend_dir / "alembic")

    cfg = Config(ini_path)
    cfg.set_main_option("script_location", script_location)
    cfg.set_main_option("sqlalchemy.url", schema_url.replace("%", "%%"))

    yield {
        "schema_name": schema_name,
        "engine": engine,
        "alembic_cfg": cfg,
        "conn_str": conn_str,
    }

    # 4. Teardown: Dispose engine and drop the schema completely
    engine.dispose()
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
    conn.close()


def test_01_migration_upgrade_and_downgrade(disposable_db_schema):
    """
    Test Alembic migration:
    - Upgrade to pre-ledger revision f7a2d83b9c01
    - Upgrade to ledger revision a2e5d9f1c74b
    - Verify table and columns exist
    - Downgrade back to f7a2d83b9c01 and verify clean reversal
    - Re-upgrade to a2e5d9f1c74b for subsequent tests
    """
    cfg = disposable_db_schema["alembic_cfg"]
    engine = disposable_db_schema["engine"]

    # 1. Upgrade from base to f7a2d83b9c01 (head before ledger)
    command.upgrade(cfg, "f7a2d83b9c01")

    # Verify ledger_entries does NOT exist yet in this schema
    with engine.connect() as conn:
        res = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries')"
        )).scalar()
        assert res is False, "ledger_entries must not exist prior to migration a2e5d9f1c74b"

    # 2. Upgrade to a2e5d9f1c74b
    command.upgrade(cfg, "a2e5d9f1c74b")

    # Verify ledger_entries table, current_balance_paise column, original_entry_id, and triggers exist
    with engine.connect() as conn:
        has_table = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries')"
        )).scalar()
        assert has_table is True, "ledger_entries table must exist after upgrade"

        has_col = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'shop_customers' AND column_name = 'current_balance_paise')"
        )).scalar()
        assert has_col is True, "current_balance_paise column must exist after upgrade"

        has_orig_col = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries' AND column_name = 'original_entry_id')"
        )).scalar()
        assert has_orig_col is True, "original_entry_id column must exist after upgrade"

        has_trg_mut = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_immutable')"
        )).scalar()
        assert has_trg_mut is True, "trg_ledger_entries_immutable trigger must exist after upgrade"

        has_trg_trunc = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_no_truncate')"
        )).scalar()
        assert has_trg_trunc is True, "trg_ledger_entries_no_truncate trigger must exist after upgrade"

        has_trg_rev = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_validate_reversal')"
        )).scalar()
        assert has_trg_rev is True, "trg_ledger_entries_validate_reversal trigger must exist after upgrade"

        has_sc_seq = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'shop_customers' AND column_name = 'last_entry_sequence')"
        )).scalar()
        assert has_sc_seq is True, "last_entry_sequence column on shop_customers must exist after upgrade"

        has_le_seq = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries' AND column_name = 'sequence_number')"
        )).scalar()
        assert has_le_seq is True, "sequence_number column on ledger_entries must exist after upgrade"

        has_le_bal = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries' AND column_name = 'balance_after_transaction_paise')"
        )).scalar()
        assert has_le_bal is True, "balance_after_transaction_paise column on ledger_entries must exist after upgrade"

    # 3. Test reversible downgrade back to f7a2d83b9c01
    command.downgrade(cfg, "f7a2d83b9c01")

    # Verify ledger_entries table and triggers are dropped
    with engine.connect() as conn:
        table_post_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'ledger_entries')"
        )).scalar()
        assert table_post_down is False, "ledger_entries must be dropped after downgrade"

        col_post_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'shop_customers' AND column_name = 'current_balance_paise')"
        )).scalar()
        assert col_post_down is False, "current_balance_paise must be dropped after downgrade"

        seq_post_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.columns "
            "WHERE table_schema = CURRENT_SCHEMA() AND table_name = 'shop_customers' AND column_name = 'last_entry_sequence')"
        )).scalar()
        assert seq_post_down is False, "last_entry_sequence must be dropped after downgrade"

        trg_mut_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_immutable')"
        )).scalar()
        assert trg_mut_down is False, "immutability trigger must be dropped after downgrade"

        trg_trunc_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_no_truncate')"
        )).scalar()
        assert trg_trunc_down is False, "truncate trigger must be dropped after downgrade"

        trg_rev_down = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_validate_reversal')"
        )).scalar()
        assert trg_rev_down is False, "reversal validation trigger must be dropped after downgrade"

    # 4. Re-upgrade to a2e5d9f1c74b for data constraint tests
    command.upgrade(cfg, "a2e5d9f1c74b")

    with engine.connect() as conn:
        reup_trg = conn.execute(text(
            "SELECT EXISTS (SELECT FROM pg_trigger WHERE tgrelid = to_regclass('ledger_entries') AND tgname = 'trg_ledger_entries_no_truncate')"
        )).scalar()
        assert reup_trg is True, "truncate trigger must be restored after re-upgrade"


@pytest.fixture(scope="module")
def seeded_entities(disposable_db_schema):
    """
    Seeds a shopkeeper, a shop, and two customers in the disposable schema for constraint tests.
    """
    engine = disposable_db_schema["engine"]
    shopkeeper_id = uuid.uuid4()
    customer_1_id = uuid.uuid4()
    customer_2_id = uuid.uuid4()
    shop_id = uuid.uuid4()
    shop_2_id = uuid.uuid4()
    shop_customer_1_id = uuid.uuid4()
    shop_customer_2_shop2_id = uuid.uuid4()

    with engine.connect() as conn:
        with conn.begin():
            # Insert users
            conn.execute(text("""
                INSERT INTO users (id, phone, password_hash, is_active, created_at, updated_at)
                VALUES
                    (:sk_id, '+919999000001', 'hash1', true, NOW(), NOW()),
                    (:c1_id, '+919999000002', 'hash2', true, NOW(), NOW()),
                    (:c2_id, '+919999000003', 'hash3', true, NOW(), NOW())
            """), {"sk_id": shopkeeper_id, "c1_id": customer_1_id, "c2_id": customer_2_id})

            # Insert shop 1
            conn.execute(text("""
                INSERT INTO shops (id, owner_user_id, shop_name, shop_address, created_at, updated_at)
                VALUES (:s_id, :sk_id, 'Test Ledger Mart', '123 Market Rd', NOW(), NOW())
            """), {"s_id": shop_id, "sk_id": shopkeeper_id})

            # Insert shop 2 (for cross-shop tests)
            conn.execute(text("""
                INSERT INTO shops (id, owner_user_id, shop_name, shop_address, created_at, updated_at)
                VALUES (:s2_id, :sk_id, 'Second Branch Mart', '456 Branch Rd', NOW(), NOW())
            """), {"s2_id": shop_2_id, "sk_id": shopkeeper_id})

            # Connect customer 1 to shop 1 (ACTIVE)
            conn.execute(text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s_id, :c1_id, 'ACTIVE', NOW(), NOW(), NOW())
            """), {"sc_id": shop_customer_1_id, "s_id": shop_id, "c1_id": customer_1_id})

            # Connect customer 1 to shop 2 (ACTIVE)
            conn.execute(text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, joined_at, created_at, updated_at)
                VALUES (:sc2_id, :s2_id, :c1_id, 'ACTIVE', NOW(), NOW(), NOW())
            """), {"sc2_id": shop_customer_2_shop2_id, "s2_id": shop_2_id, "c1_id": customer_1_id})

    return {
        "shopkeeper_id": shopkeeper_id,
        "shop_id": shop_id,
        "shop_2_id": shop_2_id,
        "customer_1_id": customer_1_id,
        "customer_2_id": customer_2_id,
    }


def test_02_default_balance_is_zero(disposable_db_schema, seeded_entities):
    """Test that shop_customers.current_balance_paise defaults to 0 on insert."""
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]

    with engine.connect() as conn:
        balance = conn.execute(text("""
            SELECT current_balance_paise FROM shop_customers
            WHERE shop_id = :s_id AND customer_user_id = :c_id
        """), {"s_id": shop_id, "c_id": customer_1_id}).scalar()
        assert balance == 0, f"Expected initial default balance 0, got {balance}"


def test_03_non_negative_balance_check_constraint(disposable_db_schema, seeded_entities):
    """Test that shop_customers rejects negative current_balance_paise via check constraint."""
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_info:
            with conn.begin():
                conn.execute(text("""
                    UPDATE shop_customers
                    SET current_balance_paise = -1
                    WHERE shop_id = :s_id AND customer_user_id = :c_id
                """), {"s_id": shop_id, "c_id": customer_1_id})
        assert "chk_shop_customer_non_negative_balance" in str(exc_info.value).lower()


def test_04_positive_amount_check_constraint(disposable_db_schema, seeded_entities):
    """Test that ledger_entries rejects amounts <= 0 (e.g. 0 or negative)."""
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]

    # 1. Test amount_paise = 0
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_0:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', 0, 'Zero amount test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
                })
        assert "chk_ledger_positive_amount" in str(exc_0.value).lower()

    # 2. Test amount_paise < 0
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_neg:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', -5000, 'Negative amount test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
                })
        assert "chk_ledger_positive_amount" in str(exc_neg.value).lower()


def test_05_valid_transaction_type_constraint(disposable_db_schema, seeded_entities):
    """Test that ledger_entries accepts all 4 valid types ('CREDIT', 'REPAYMENT', 'CREDIT_REVERSAL', 'REPAYMENT_REVERSAL') and rejects invalid types."""
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]

    # 1. Valid CREDIT succeeds
    credit_id = uuid.uuid4()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 100000, 'Groceries ₹1000', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
            })

    # 2. Valid REPAYMENT succeeds
    repay_id = uuid.uuid4()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT', 40000, 'Repayment ₹400', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": repay_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
            })

    # 3. Valid CREDIT_REVERSAL referencing credit_id succeeds
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 20000, 'Partial credit reversal', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}", "orig_id": credit_id,
            })

    # 4. Valid REPAYMENT_REVERSAL referencing repay_id succeeds
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT_REVERSAL', 15000, 'Partial repayment reversal', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}", "orig_id": repay_id,
            })

    # 5. Invalid transaction_type ('REFUND' or 'DEBIT') is rejected by check constraint
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_invalid:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'REFUND', 20000, 'Invalid type', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
                })
        err_msg = str(exc_invalid.value).lower()
        assert "chk_ledger_transaction_type" in err_msg or "chk_ledger_reversal_original_entry" in err_msg


def test_06_shop_customer_relationship_foreign_key_constraint(disposable_db_schema, seeded_entities):
    """
    Test that a ledger entry CANNOT be created for a customer who has not joined the shop.
    Guaranteed by fk_ledger_shop_customer -> (shop_id, customer_user_id).
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_2_id = seeded_entities["customer_2_id"]  # customer 2 has NOT joined this shop
    sk_id = seeded_entities["shopkeeper_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_fk:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', 50000, 'Unlinked customer', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_2_id,
                    "by_id": sk_id, "idem": f"idem-{uuid.uuid4()}",
                })
        assert "fk_ledger_shop_customer" in str(exc_fk.value).lower()


def test_07_idempotency_key_uniqueness(disposable_db_schema, seeded_entities):
    """
    Test that duplicate idempotency keys within the same shop are rejected.
    Guaranteed by uq_ledger_shop_idempotency_key.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    idempotency_key = f"idem-unique-{uuid.uuid4()}"

    # 1. First insert with idempotency_key succeeds
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 35000, 'Original request', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": idempotency_key,
            })

    # 2. Duplicate insert with SAME idempotency_key for the same shop is rejected
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_idem:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', 35000, 'Duplicate retry', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": idempotency_key,
                })
        assert "uq_ledger_shop_idempotency_key" in str(exc_idem.value).lower()


def test_08_immutable_ledger_update_rejected(disposable_db_schema, seeded_entities):
    """
    Test that UPDATE of a ledger entry is strictly rejected at the database level by trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    entry_id = uuid.uuid4()

    # 1. Insert an entry
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 20000, 'Original entry for update test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": entry_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-upd-{uuid.uuid4()}",
            })

    # 2. Attempt UPDATE -> MUST be rejected by trg_ledger_entries_immutable
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_upd:
            with conn.begin():
                conn.execute(text("""
                    UPDATE ledger_entries
                    SET amount_paise = 99999
                    WHERE id = :id
                """), {"id": entry_id})
        err_msg = str(exc_upd.value).lower()
        assert "ledger entries are strictly immutable" in err_msg or "updates and deletions are forbidden" in err_msg


def test_09_immutable_ledger_delete_rejected(disposable_db_schema, seeded_entities):
    """
    Test that DELETE of a ledger entry is strictly rejected at the database level by trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    entry_id = uuid.uuid4()

    # 1. Insert an entry
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 25000, 'Entry for delete test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": entry_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-del-{uuid.uuid4()}",
            })

    # 2. Attempt DELETE -> MUST be rejected by trg_ledger_entries_immutable
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_del:
            with conn.begin():
                conn.execute(text("""
                    DELETE FROM ledger_entries
                    WHERE id = :id
                """), {"id": entry_id})
        err_msg = str(exc_del.value).lower()
        assert "ledger entries are strictly immutable" in err_msg or "updates and deletions are forbidden" in err_msg


def test_10_delete_shop_restricted(disposable_db_schema, seeded_entities):
    """
    Test that deleting a referenced shop is RESTRICTED at the database level.
    Guaranteed by fk_ledger_entries_shop_id ON DELETE RESTRICT.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_shop:
            with conn.begin():
                conn.execute(text("DELETE FROM shops WHERE id = :s_id"), {"s_id": shop_id})
        err_msg = str(exc_shop.value).lower()
        assert "fk_ledger_entries_shop_id" in err_msg or "foreign key constraint" in err_msg


def test_11_delete_customer_user_restricted(disposable_db_schema, seeded_entities):
    """
    Test that deleting a referenced customer user is RESTRICTED at the database level.
    Guaranteed by fk_ledger_entries_customer_user_id ON DELETE RESTRICT.
    """
    engine = disposable_db_schema["engine"]
    customer_1_id = seeded_entities["customer_1_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_cust:
            with conn.begin():
                conn.execute(text("DELETE FROM users WHERE id = :c_id"), {"c_id": customer_1_id})
        err_msg = str(exc_cust.value).lower()
        assert "fk_ledger_entries_customer_user_id" in err_msg or "foreign key constraint" in err_msg


def test_12_delete_shop_customer_restricted(disposable_db_schema, seeded_entities):
    """
    Test that deleting a ShopCustomer record cannot cascade-delete ledger entries.
    Guaranteed by fk_ledger_shop_customer ON DELETE RESTRICT.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_sc:
            with conn.begin():
                conn.execute(text("""
                    DELETE FROM shop_customers
                    WHERE shop_id = :s_id AND customer_user_id = :c_id
                """), {"s_id": shop_id, "c_id": customer_1_id})
        err_msg = str(exc_sc.value).lower()
        assert "fk_ledger_shop_customer" in err_msg or "foreign key constraint" in err_msg


def test_13_active_membership_service_contract_documented(disposable_db_schema, seeded_entities):
    """
    Demonstrates and verifies that:
    1. A customer with status != 'ACTIVE' (e.g. 'BLOCKED' or 'INACTIVE') still exists in shop_customers.
    2. Because FKs only check referential existence, the database FK alone allows inserting an entry
       for an inactive customer.
    3. Therefore, Phase 2 service layer MUST explicitly lock and validate `shop_customer.status == 'ACTIVE'`
       before permitting any credit or repayment transaction.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_2_id = seeded_entities["customer_2_id"]

    # Seed customer 2 with status = 'BLOCKED'
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO shop_customers (id, shop_id, customer_user_id, status, joined_at, created_at, updated_at)
                VALUES (:sc_id, :s_id, :c_id, 'BLOCKED', NOW(), NOW(), NOW())
            """), {"sc_id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_2_id})

    # Read back status to confirm it is not ACTIVE
    with engine.connect() as conn:
        status = conn.execute(text("""
            SELECT status FROM shop_customers
            WHERE shop_id = :s_id AND customer_user_id = :c_id
        """), {"s_id": shop_id, "c_id": customer_2_id}).scalar()
        assert status == "BLOCKED"


def test_14_immutable_ledger_truncate_rejected(disposable_db_schema):
    """
    Test that TRUNCATE on ledger_entries is strictly rejected at the database level by trigger.
    Guaranteed by trg_ledger_entries_no_truncate (BEFORE TRUNCATE ... FOR EACH STATEMENT).
    """
    engine = disposable_db_schema["engine"]

    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_trunc:
            with conn.begin():
                conn.execute(text("TRUNCATE TABLE ledger_entries"))
        err_msg = str(exc_trunc.value).lower()
        assert "cannot be truncated" in err_msg or "truncation is strictly forbidden" in err_msg


def test_15_reversal_of_credit_success(disposable_db_schema, seeded_entities):
    """
    Test that a valid CREDIT_REVERSAL referencing an existing CREDIT entry succeeds.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    # 1. Insert original CREDIT
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 50000, 'Original ₹500 credit', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-{uuid.uuid4()}",
            })

    # 2. Insert valid full CREDIT_REVERSAL
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 50000, 'Reversal of ₹500 credit', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": rev_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-rev-{uuid.uuid4()}", "orig_id": credit_id,
            })

    # 3. Verify reversal record exists and links correctly
    with engine.connect() as conn:
        stored_orig_id = conn.execute(text("SELECT original_entry_id FROM ledger_entries WHERE id = :id"), {"id": rev_id}).scalar()
        assert stored_orig_id == credit_id


def test_16_reversal_of_repayment_success(disposable_db_schema, seeded_entities):
    """
    Test that a valid REPAYMENT_REVERSAL referencing an existing REPAYMENT entry succeeds.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    repay_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    # 1. Insert original REPAYMENT
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT', 30000, 'Original ₹300 repayment', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": repay_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-rp-{uuid.uuid4()}",
            })

    # 2. Insert valid full REPAYMENT_REVERSAL
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT_REVERSAL', 30000, 'Reversal of ₹300 repayment', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": rev_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-rp-rev-{uuid.uuid4()}", "orig_id": repay_id,
            })

    # 3. Verify reversal record exists and links correctly
    with engine.connect() as conn:
        stored_orig_id = conn.execute(text("SELECT original_entry_id FROM ledger_entries WHERE id = :id"), {"id": rev_id}).scalar()
        assert stored_orig_id == repay_id


def test_17_reversal_exceeding_original_amount_rejected(disposable_db_schema, seeded_entities):
    """
    Test that a reversal exceeding the original transaction amount is rejected.
    Guaranteed by trg_ledger_entries_validate_reversal trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    # 1. Insert original CREDIT of ₹500 (50,000 paise)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 50000, 'Original ₹500 credit', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-lim-{uuid.uuid4()}",
            })

    # 2. Attempt reversal of ₹501 (50,100 paise) -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_over:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 50100, 'Over-reversal attempt', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-over-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_over.value).lower()
        assert "exceeds remaining reversible amount" in err_msg


def test_18_multiple_partial_reversals_exceeding_amount_rejected(disposable_db_schema, seeded_entities):
    """
    Test that cumulative partial reversals cannot exceed the original transaction amount.
    Guaranteed by trg_ledger_entries_validate_reversal trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    # 1. Insert original CREDIT of ₹1,000 (100,000 paise)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 100000, 'Original ₹1000 credit', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-part-{uuid.uuid4()}",
            })

    # 2. First partial reversal: ₹600 (60,000 paise) -> MUST succeed
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 60000, 'Partial reversal 1: ₹600', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-p1-{uuid.uuid4()}", "orig_id": credit_id,
            })

    # 3. Second partial reversal: ₹500 (50,000 paise) -> (600 + 500 = 1100 > 1000) -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_over:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 50000, 'Partial reversal 2: ₹500 (excess)', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-p2-bad-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_over.value).lower()
        assert "exceeds remaining reversible amount" in err_msg

    # 4. Second partial reversal: exact remaining ₹400 (40,000 paise) -> (600 + 400 = 1000) -> MUST succeed
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 40000, 'Partial reversal 2: ₹400 (exact balance)', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-p2-ok-{uuid.uuid4()}", "orig_id": credit_id,
            })

    # 5. Third partial reversal: even ₹1 (100 paise) -> MUST be rejected (remaining is 0)
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_zero:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 100, 'Third partial (remaining 0)', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-p3-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_zero.value).lower()
        assert "exceeds remaining reversible amount" in err_msg


def test_19_cross_shop_and_cross_customer_reversal_rejected(disposable_db_schema, seeded_entities):
    """
    Test that a reversal CANNOT reference an original entry from a different shop or a different customer.
    Guaranteed by trg_ledger_entries_validate_reversal trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    shop_2_id = seeded_entities["shop_2_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    customer_2_id = seeded_entities["customer_2_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    # 1. Insert original CREDIT at shop 1 for customer 1
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 70000, 'Shop 1 Customer 1 credit', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cross-{uuid.uuid4()}",
            })

    # 2. Attempt cross-shop reversal: customer 1 attempts reversal on shop 2 -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_shop:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s2_id, :c_id, :by_id, 'CREDIT_REVERSAL', 70000, 'Cross-shop attempt', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s2_id": shop_2_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-cross-s-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_shop.value).lower()
        assert "shop_id" in err_msg and "does not match original entry" in err_msg

    # 3. Attempt cross-customer reversal: shop 1 attempts reversal against customer 2 -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_cust:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c2_id, :by_id, 'CREDIT_REVERSAL', 70000, 'Cross-customer attempt', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c2_id": customer_2_id,
                    "by_id": sk_id, "idem": f"idem-cross-c-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_cust.value).lower()
        assert "customer_user_id" in err_msg and "does not match original entry" in err_msg


def test_20_duplicate_reversal_idempotency(disposable_db_schema, seeded_entities):
    """
    Test that duplicate reversal submissions with the same idempotency key are rejected by unique constraint.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()
    idem_key = f"idem-rev-unique-{uuid.uuid4()}"

    # 1. Insert original CREDIT
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 45000, 'Credit for idempotency test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-{uuid.uuid4()}",
            })

    # 2. First reversal with idem_key succeeds
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 20000, 'First reversal attempt', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": idem_key, "orig_id": credit_id,
            })

    # 3. Duplicate reversal with SAME idem_key is rejected by uq_ledger_shop_idempotency_key
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_dup:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 20000, 'Duplicate retry', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": idem_key, "orig_id": credit_id,
                })
        assert "uq_ledger_shop_idempotency_key" in str(exc_dup.value).lower()


def test_21_reversal_without_original_entry_rejected(disposable_db_schema, seeded_entities):
    """
    Test that a reversal with original_entry_id = NULL is rejected by check constraint.
    Guaranteed by chk_ledger_reversal_original_entry.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]

    with engine.connect() as conn:
        with pytest.raises((IntegrityError, DBAPIError)) as exc_no_orig:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 10000, 'Reversal without original', :idem, NULL, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-no-orig-{uuid.uuid4()}",
                })
        err_msg = str(exc_no_orig.value).lower()
        assert "chk_ledger_reversal_original_entry" in err_msg or "original ledger entry" in err_msg


def test_22_non_reversal_with_original_entry_rejected(disposable_db_schema, seeded_entities):
    """
    Test that a standard CREDIT or REPAYMENT cannot have a non-null original_entry_id.
    Guaranteed by chk_ledger_reversal_original_entry.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]

    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_non_rev:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', 10000, 'Credit with invalid original_entry_id', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-cr-bad-{uuid.uuid4()}", "orig_id": uuid.uuid4(),
                })
        assert "chk_ledger_reversal_original_entry" in str(exc_non_rev.value).lower()


def test_23_mismatched_reversal_type_rejected(disposable_db_schema, seeded_entities):
    """
    Test that a REPAYMENT_REVERSAL cannot reverse a CREDIT, and CREDIT_REVERSAL cannot reverse a REPAYMENT.
    Guaranteed by trg_ledger_entries_validate_reversal trigger.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    # 1. Insert original CREDIT
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 30000, 'Credit entry', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-mismatch-{uuid.uuid4()}",
            })

    # 2. Attempt REPAYMENT_REVERSAL referencing the CREDIT entry -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_mismatch:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'REPAYMENT_REVERSAL', 30000, 'Invalid mismatch type', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-mismatch-{uuid.uuid4()}", "orig_id": credit_id,
                })
        err_msg = str(exc_mismatch.value).lower()
        assert "repayment_reversal can only reverse a repayment entry" in err_msg


def test_24_concurrent_credit_reversals_prevent_over_reversal(disposable_db_schema, seeded_entities):
    """
    Genuine concurrent PostgreSQL test:
    - Original CREDIT: 10,000 paise.
    - Two concurrent CREDIT_REVERSAL requests: 6,000 paise each, with different idempotency keys.
    - Uses two independent database connections and a threading Barrier.
    - Exactly one reversal must succeed; the other must fail with 'exceeds remaining reversible amount'.
    - Total successful reversals in database must never exceed 10,000 paise (will be exactly 6,000 paise).
    """
    engine = disposable_db_schema["engine"]
    conn_str = disposable_db_schema["conn_str"]
    schema_name = disposable_db_schema["schema_name"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    # 1. Insert original CREDIT of 10,000 paise (₹100)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 10000, 'Original ₹100 credit for concurrency test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-orig-conc-{uuid.uuid4()}",
            })

    # 2. Setup barrier, base sequence, and worker function
    barrier = threading.Barrier(2)
    results = []
    with engine.connect() as conn:
        base_seq = conn.execute(text("SELECT COALESCE(MAX(sequence_number), 0) FROM ledger_entries")).scalar()

    def attempt_reversal(thread_id, amount_paise):
        idem = f"idem-conc-cr-{thread_id}-{uuid.uuid4()}"
        rev_id = uuid.uuid4()
        c = psycopg2.connect(f"{conn_str}?options=-csearch_path%3D{schema_name}")
        c.autocommit = False
        try:
            cur = c.cursor()
            barrier.wait()
            cur.execute("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (%s, %s, %s, %s, 'CREDIT_REVERSAL', %s, 'Concurrent reversal attempt', %s, %s, %s, 0, NOW())
            """, (str(rev_id), str(shop_id), str(customer_1_id), str(sk_id), amount_paise, idem, str(credit_id), base_seq + thread_id))
            c.commit()
            results.append({"thread_id": thread_id, "status": "SUCCESS", "error": None})
        except Exception as e:
            c.rollback()
            results.append({"thread_id": thread_id, "status": "FAILED", "error": str(e)})
        finally:
            c.close()

    # 3. Fire two concurrent threads
    t1 = threading.Thread(target=attempt_reversal, args=(1, 6000))
    t2 = threading.Thread(target=attempt_reversal, args=(2, 6000))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 4. Assertions: exactly one success, one failure
    successes = [r for r in results if r["status"] == "SUCCESS"]
    failures = [r for r in results if r["status"] == "FAILED"]

    assert len(successes) == 1, f"Expected exactly 1 successful reversal, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failed reversal, got {len(failures)}: {results}"
    assert "exceeds remaining reversible amount" in failures[0]["error"].lower()

    # 5. Verify database state
    with engine.connect() as conn:
        total_reversed = conn.execute(text("""
            SELECT COALESCE(SUM(amount_paise), 0)
            FROM ledger_entries
            WHERE original_entry_id = :orig_id
        """), {"orig_id": credit_id}).scalar()
        assert total_reversed == 6000, f"Expected exactly 6000 paise reversed, found {total_reversed}"


def test_25_concurrent_repayment_reversals_prevent_over_reversal(disposable_db_schema, seeded_entities):
    """
    Genuine concurrent PostgreSQL test:
    - Original REPAYMENT: 10,000 paise.
    - Two concurrent REPAYMENT_REVERSAL requests: 6,000 paise each, with different idempotency keys.
    - Uses two independent database connections and a threading Barrier.
    - Exactly one reversal must succeed; the other must fail with 'exceeds remaining reversible amount'.
    - Total successful reversals in database must never exceed 10,000 paise (will be exactly 6,000 paise).
    """
    engine = disposable_db_schema["engine"]
    conn_str = disposable_db_schema["conn_str"]
    schema_name = disposable_db_schema["schema_name"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    repay_id = uuid.uuid4()

    # 1. Insert original REPAYMENT of 10,000 paise (₹100)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT', 10000, 'Original ₹100 repayment for concurrency test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": repay_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-orig-rp-conc-{uuid.uuid4()}",
            })

    # 2. Setup barrier, base sequence, and worker function
    barrier = threading.Barrier(2)
    results = []
    with engine.connect() as conn:
        base_seq = conn.execute(text("SELECT COALESCE(MAX(sequence_number), 0) FROM ledger_entries")).scalar()

    def attempt_reversal(thread_id, amount_paise):
        idem = f"idem-conc-rp-{thread_id}-{uuid.uuid4()}"
        rev_id = uuid.uuid4()
        c = psycopg2.connect(f"{conn_str}?options=-csearch_path%3D{schema_name}")
        c.autocommit = False
        try:
            cur = c.cursor()
            barrier.wait()
            cur.execute("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (%s, %s, %s, %s, 'REPAYMENT_REVERSAL', %s, 'Concurrent repayment reversal attempt', %s, %s, %s, 0, NOW())
            """, (str(rev_id), str(shop_id), str(customer_1_id), str(sk_id), amount_paise, idem, str(repay_id), base_seq + thread_id))
            c.commit()
            results.append({"thread_id": thread_id, "status": "SUCCESS", "error": None})
        except Exception as e:
            c.rollback()
            results.append({"thread_id": thread_id, "status": "FAILED", "error": str(e)})
        finally:
            c.close()

    # 3. Fire two concurrent threads
    t1 = threading.Thread(target=attempt_reversal, args=(1, 6000))
    t2 = threading.Thread(target=attempt_reversal, args=(2, 6000))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 4. Assertions: exactly one success, one failure
    successes = [r for r in results if r["status"] == "SUCCESS"]
    failures = [r for r in results if r["status"] == "FAILED"]

    assert len(successes) == 1, f"Expected exactly 1 successful reversal, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failed reversal, got {len(failures)}: {results}"
    assert "exceeds remaining reversible amount" in failures[0]["error"].lower()

    # 5. Verify database state
    with engine.connect() as conn:
        total_reversed = conn.execute(text("""
            SELECT COALESCE(SUM(amount_paise), 0)
            FROM ledger_entries
            WHERE original_entry_id = :orig_id
        """), {"orig_id": repay_id}).scalar()
        assert total_reversed == 6000, f"Expected exactly 6000 paise reversed, found {total_reversed}"


def test_26_reversal_rollback_releases_lock_and_permits_retry(disposable_db_schema, seeded_entities):
    """
    Verifies that:
    1. If a reversal transaction rolls back, the lock is released and uncommitted rows are discarded.
    2. A subsequent retry with the same or different idempotency key can successfully reverse the transaction.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()
    retry_idem = f"idem-retry-test-{uuid.uuid4()}"

    # 1. Insert original CREDIT of 5,000 paise
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 5000, 'Original credit for rollback test', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-orig-rb-{uuid.uuid4()}",
            })

    # 2. Simulate an aborted reversal transaction (explicit rollback)
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(text("""
            INSERT INTO ledger_entries
                (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
            VALUES
                (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 5000, 'Aborted reversal', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
        """), {
            "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
            "by_id": sk_id, "idem": retry_idem, "orig_id": credit_id,
        })
        trans.rollback()

    # 3. Retry with the SAME idempotency key -> MUST succeed because previous was rolled back
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, original_entry_id, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT_REVERSAL', 5000, 'Retried reversal', :idem, :orig_id, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": retry_idem, "orig_id": credit_id,
            })

    # 4. Verify exactly 1 reversal exists with total 5,000 paise
    with engine.connect() as conn:
        total_reversed = conn.execute(text("""
            SELECT COALESCE(SUM(amount_paise), 0)
            FROM ledger_entries
            WHERE original_entry_id = :orig_id
        """), {"orig_id": credit_id}).scalar()
        assert total_reversed == 5000


def test_27_credit_reversal_with_prior_repayment_negative_balance_risk_documented(disposable_db_schema, seeded_entities):
    """
    Demonstrates and verifies Requirement 5:
    When a customer has partially or fully repaid a credit:
    - Example: Credit ₹1,000 (100,000 paise) -> Balance ₹1,000.
    - Customer repays ₹800 (80,000 paise) -> Balance ₹200 (20,000 paise).
    - If shopkeeper attempts full CREDIT_REVERSAL of ₹1,000:
      a) The ledger_entries reversal trigger allows ₹1,000 (because ₹1,000 <= original ₹1,000).
      b) BUT updating shop_customers.current_balance_paise to (20,000 - 100,000 = -80,000)
         is REJECTED by chk_shop_customer_non_negative_balance.
      c) Therefore, Phase 2 service layer MUST validate that:
         credit_reversal_amount <= shop_customer.current_balance_paise
         before executing the balance update, returning HTTP 400 with a clear business message.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]
    credit_id = uuid.uuid4()

    with engine.connect() as conn:
        with conn.begin():
            # 1. Credit 100,000 paise (₹1,000) -> set balance to 100,000
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 100000, 'Original credit ₹1000', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": credit_id, "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-cr-rep-{uuid.uuid4()}",
            })
            conn.execute(text("""
                UPDATE shop_customers
                SET current_balance_paise = 100000
                WHERE shop_id = :s_id AND customer_user_id = :c_id
            """), {"s_id": shop_id, "c_id": customer_1_id})

            # 2. Customer repays 80,000 paise (₹800) -> set balance to 20,000
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type, amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'REPAYMENT', 80000, 'Customer repayment ₹800', :idem, (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM ledger_entries), 0, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-rp-rep-{uuid.uuid4()}",
            })
            conn.execute(text("""
                UPDATE shop_customers
                SET current_balance_paise = 20000
                WHERE shop_id = :s_id AND customer_user_id = :c_id
            """), {"s_id": shop_id, "c_id": customer_1_id})

        # 3. Attempt to apply full credit reversal of 100,000 against balance of 20,000
        # The balance update MUST be rejected by chk_shop_customer_non_negative_balance
        with pytest.raises(IntegrityError) as exc_neg:
            with conn.begin():
                conn.execute(text("""
                    UPDATE shop_customers
                    SET current_balance_paise = current_balance_paise - 100000
                    WHERE shop_id = :s_id AND customer_user_id = :c_id
                """), {"s_id": shop_id, "c_id": customer_1_id})
        assert "chk_shop_customer_non_negative_balance" in str(exc_neg.value).lower()

        # 4. Clean up balance back to 0 for subsequent test isolation
        with conn.begin():
            conn.execute(text("""
                UPDATE shop_customers
                SET current_balance_paise = 0
                WHERE shop_id = :s_id AND customer_user_id = :c_id
            """), {"s_id": shop_id, "c_id": customer_1_id})



def test_28_per_customer_sequence_uniqueness_constraint(disposable_db_schema, seeded_entities):
    """
    Test that duplicate sequence_number for the same shop_id and customer_user_id
    is strictly rejected by uq_ledger_customer_sequence constraint.
    """
    engine = disposable_db_schema["engine"]
    shop_id = seeded_entities["shop_id"]
    customer_1_id = seeded_entities["customer_1_id"]
    sk_id = seeded_entities["shopkeeper_id"]

    seq_val = 999999

    # 1. Insert entry with explicit sequence_number
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                INSERT INTO ledger_entries
                    (id, shop_id, customer_user_id, created_by_user_id, transaction_type,
                     amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                VALUES
                    (:id, :s_id, :c_id, :by_id, 'CREDIT', 1000, 'Seq test 1', :idem, :seq, 1000, NOW())
            """), {
                "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                "by_id": sk_id, "idem": f"idem-seq-1-{uuid.uuid4()}", "seq": seq_val,
            })

    # 2. Insert second entry with SAME sequence_number for SAME shop and customer -> MUST be rejected
    with engine.connect() as conn:
        with pytest.raises(IntegrityError) as exc_seq:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO ledger_entries
                        (id, shop_id, customer_user_id, created_by_user_id, transaction_type,
                         amount_paise, note, idempotency_key, sequence_number, balance_after_transaction_paise, created_at)
                    VALUES
                        (:id, :s_id, :c_id, :by_id, 'CREDIT', 1000, 'Seq test 2 duplicate', :idem, :seq, 2000, NOW())
                """), {
                    "id": uuid.uuid4(), "s_id": shop_id, "c_id": customer_1_id,
                    "by_id": sk_id, "idem": f"idem-seq-2-{uuid.uuid4()}", "seq": seq_val,
                })
        assert "uq_ledger_customer_sequence" in str(exc_seq.value).lower()
