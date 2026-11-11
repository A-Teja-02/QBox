"""add_ledger_entries_and_customer_balance

Revision ID: a2e5d9f1c74b
Revises: f7a2d83b9c01
Create Date: 2026-11-10 13:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2e5d9f1c74b'
down_revision: Union[str, Sequence[str], None] = 'f7a2d83b9c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema:
    1. Add current_balance_paise to shop_customers (BIGINT, NOT NULL, DEFAULT 0, CHECK >= 0).
    2. Create ledger_entries table with immutable transaction fields and integrity constraints.
    3. Create indexes for fast retrieval by shop, customer, and timestamps.
    """
    # 1. Update shop_customers with cached balance, sequence counter, and non-negative constraint
    op.add_column(
        'shop_customers',
        sa.Column('current_balance_paise', sa.BigInteger(), server_default='0', nullable=False),
    )
    op.add_column(
        'shop_customers',
        sa.Column('last_entry_sequence', sa.BigInteger(), server_default='0', nullable=False),
    )
    op.create_check_constraint(
        'chk_shop_customer_non_negative_balance',
        'shop_customers',
        'current_balance_paise >= 0',
    )

    # 2. Create ledger_entries table
    op.create_table(
        'ledger_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('shop_id', sa.Uuid(), nullable=False),
        sa.Column('customer_user_id', sa.Uuid(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('transaction_type', sa.String(length=32), nullable=False),
        sa.Column('amount_paise', sa.BigInteger(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('original_entry_id', sa.Uuid(), nullable=True),
        sa.Column('sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('balance_after_transaction_paise', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['shop_id'],
            ['shops.id'],
            name='fk_ledger_entries_shop_id',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['customer_user_id'],
            ['users.id'],
            name='fk_ledger_entries_customer_user_id',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            ['users.id'],
            name='fk_ledger_entries_created_by_user_id',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['shop_id', 'customer_user_id'],
            ['shop_customers.shop_id', 'shop_customers.customer_user_id'],
            name='fk_ledger_shop_customer',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['original_entry_id'],
            ['ledger_entries.id'],
            name='fk_ledger_entries_original_entry_id',
            ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "transaction_type IN ('CREDIT', 'REPAYMENT', 'CREDIT_REVERSAL', 'REPAYMENT_REVERSAL')",
            name='chk_ledger_transaction_type',
        ),
        sa.CheckConstraint(
            "(transaction_type IN ('CREDIT', 'REPAYMENT') AND original_entry_id IS NULL) OR "
            "(transaction_type IN ('CREDIT_REVERSAL', 'REPAYMENT_REVERSAL') AND original_entry_id IS NOT NULL)",
            name='chk_ledger_reversal_original_entry',
        ),
        sa.CheckConstraint(
            'amount_paise > 0',
            name='chk_ledger_positive_amount',
        ),
        sa.UniqueConstraint(
            'shop_id', 'idempotency_key',
            name='uq_ledger_shop_idempotency_key',
        ),
        sa.UniqueConstraint(
            'shop_id', 'customer_user_id', 'sequence_number',
            name='uq_ledger_customer_sequence',
        ),
    )

    # 3. Create indexes
    op.create_index(
        'ix_ledger_entries_shop_id',
        'ledger_entries',
        ['shop_id'],
    )
    op.create_index(
        'ix_ledger_entries_customer_user_id',
        'ledger_entries',
        ['customer_user_id'],
    )
    op.create_index(
        'ix_ledger_entries_created_by_user_id',
        'ledger_entries',
        ['created_by_user_id'],
    )
    op.create_index(
        'ix_ledger_entries_idempotency_key',
        'ledger_entries',
        ['idempotency_key'],
    )
    op.create_index(
        'ix_ledger_entries_original_entry_id',
        'ledger_entries',
        ['original_entry_id'],
    )
    op.create_index(
        'ix_ledger_shop_customer_created',
        'ledger_entries',
        ['shop_id', 'customer_user_id', 'created_at'],
    )
    op.create_index(
        'ix_ledger_shop_created',
        'ledger_entries',
        ['shop_id', 'created_at'],
    )
    op.create_index(
        'ix_ledger_customer_created',
        'ledger_entries',
        ['customer_user_id', 'created_at'],
    )

    # 4. Strict database-level immutability: Prevent UPDATE and DELETE on ledger_entries
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_fn_prevent_ledger_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Ledger entries are strictly immutable. Updates and deletions are forbidden.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION trg_fn_prevent_ledger_mutation();
        """
    )

    # 5. Strict database-level truncate protection: Prevent TRUNCATE on ledger_entries
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_fn_prevent_ledger_truncate()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Ledger entries table cannot be truncated. Truncation is strictly forbidden.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_no_truncate
        BEFORE TRUNCATE ON ledger_entries
        FOR EACH STATEMENT EXECUTE FUNCTION trg_fn_prevent_ledger_truncate();
        """
    )

    # 6. Database-level reversal validation: atomic check of original entry existence, shop/customer match,
    # type pairing, and cumulative amount limit
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_fn_validate_ledger_reversal()
        RETURNS TRIGGER AS $$
        DECLARE
            orig RECORD;
            already_reversed BIGINT;
        BEGIN
            IF NEW.transaction_type IN ('CREDIT_REVERSAL', 'REPAYMENT_REVERSAL') THEN
                -- Fetch and lock the referenced original entry
                SELECT * INTO orig FROM ledger_entries WHERE id = NEW.original_entry_id FOR UPDATE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Original ledger entry % not found', NEW.original_entry_id;
                END IF;

                -- Validate shop and customer match
                IF orig.shop_id <> NEW.shop_id THEN
                    RAISE EXCEPTION 'Reversal shop_id (%) does not match original entry shop_id (%)', NEW.shop_id, orig.shop_id;
                END IF;
                IF orig.customer_user_id <> NEW.customer_user_id THEN
                    RAISE EXCEPTION 'Reversal customer_user_id (%) does not match original entry customer_user_id (%)', NEW.customer_user_id, orig.customer_user_id;
                END IF;

                -- Validate transaction type pairing
                IF NEW.transaction_type = 'CREDIT_REVERSAL' AND orig.transaction_type <> 'CREDIT' THEN
                    RAISE EXCEPTION 'CREDIT_REVERSAL can only reverse a CREDIT entry (original is %)', orig.transaction_type;
                END IF;
                IF NEW.transaction_type = 'REPAYMENT_REVERSAL' AND orig.transaction_type <> 'REPAYMENT' THEN
                    RAISE EXCEPTION 'REPAYMENT_REVERSAL can only reverse a REPAYMENT entry (original is %)', orig.transaction_type;
                END IF;

                -- Calculate cumulative reversals already applied to this original entry
                SELECT COALESCE(SUM(amount_paise), 0) INTO already_reversed
                FROM ledger_entries
                WHERE original_entry_id = NEW.original_entry_id;

                IF (already_reversed + NEW.amount_paise) > orig.amount_paise THEN
                    RAISE EXCEPTION 'Reversal amount % paise exceeds remaining reversible amount % paise (original: % paise, already reversed: % paise)',
                        NEW.amount_paise, (orig.amount_paise - already_reversed), orig.amount_paise, already_reversed;
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_validate_reversal
        BEFORE INSERT ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION trg_fn_validate_ledger_reversal();
        """
    )


def downgrade() -> None:
    """
    Downgrade schema:
    WARNING: Running this downgrade in an environment with existing financial records
    will DROP the ledger_entries table and customer balance column, permanently destroying
    all financial transaction history and ledger data. Downgrade is strictly prohibited in
    production environments.
    """
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_validate_reversal ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_validate_ledger_reversal();")

    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_no_truncate ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_ledger_truncate();")

    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_immutable ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_ledger_mutation();")

    op.drop_index('ix_ledger_customer_created', table_name='ledger_entries')
    op.drop_index('ix_ledger_shop_created', table_name='ledger_entries')
    op.drop_index('ix_ledger_shop_customer_created', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_original_entry_id', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_idempotency_key', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_created_by_user_id', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_customer_user_id', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_shop_id', table_name='ledger_entries')
    op.drop_table('ledger_entries')

    op.drop_constraint('chk_shop_customer_non_negative_balance', 'shop_customers', type_='check')
    op.drop_column('shop_customers', 'last_entry_sequence')
    op.drop_column('shop_customers', 'current_balance_paise')

