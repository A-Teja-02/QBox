"""add_image_data_bytea_to_shop_payment_qrs

Revision ID: f7a2d83b9c01
Revises: eb0a8e44d7a1
Create Date: 2026-11-10 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a2d83b9c01'
down_revision: Union[str, Sequence[str], None] = 'eb0a8e44d7a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add image_data BYTEA column to shop_payment_qrs."""
    op.add_column(
        'shop_payment_qrs',
        sa.Column('image_data', sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    """
    WARNING: DESTRUCTIVE DOWNGRADE OPERATION!
    Dropping the 'image_data' column permanently deletes all binary payment QR image
    bytes stored in PostgreSQL.

    MANDATORY PRE-REQUISITE BEFORE EXECUTING THIS DOWNGRADE:
    1. Take a full verified database backup (e.g., pg_dump) or export all image bytes.
    2. Confirm that all active shops have fallback storage or image backups.
    """
    op.drop_column('shop_payment_qrs', 'image_data')

