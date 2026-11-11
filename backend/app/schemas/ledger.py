"""
Pydantic schemas for Qbox Udhaar Ledger (Phase 2).
Strict integer paise validation, ISO timestamps, and payload models.
"""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class CreateLedgerEntryRequest(BaseModel):
    """Request payload for recording a regular credit or repayment entry."""
    customer_user_id: Optional[UUID] = Field(None, description="UUID of the customer user")
    transaction_type: Literal["CREDIT", "REPAYMENT"]
    amount_paise: StrictInt = Field(..., gt=0, description="Amount in integer paise (₹1 = 100 paise), must be > 0")
    note: Optional[str] = Field(None, max_length=500, description="Optional transaction description or remark")
    idempotency_key: str = Field(..., min_length=1, max_length=128, description="Client-generated unique request identifier")


class CreateReversalRequest(BaseModel):
    """Request payload for reversing an existing ledger entry."""
    customer_user_id: Optional[UUID] = Field(None, description="UUID of the customer user")
    transaction_type: Literal["CREDIT_REVERSAL", "REPAYMENT_REVERSAL"]
    original_entry_id: UUID = Field(..., description="UUID of the original CREDIT or REPAYMENT entry to reverse")
    amount_paise: StrictInt = Field(..., gt=0, description="Amount in integer paise to reverse, must be > 0 and <= original entry amount")
    note: Optional[str] = Field(None, max_length=500, description="Mandatory/optional reason for reversal")
    idempotency_key: str = Field(..., min_length=1, max_length=128, description="Client-generated unique request identifier")


class LedgerEntryResponse(BaseModel):
    """Schema representing an immutable ledger transaction."""
    id: UUID
    shop_id: UUID
    customer_user_id: UUID
    created_by_user_id: UUID
    transaction_type: str
    amount_paise: int
    note: Optional[str] = None
    idempotency_key: str
    original_entry_id: Optional[UUID] = None
    sequence_number: int
    balance_after_transaction_paise: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerTransactionResultResponse(BaseModel):
    """Schema returned after recording or replaying a transaction."""
    entry: LedgerEntryResponse
    current_balance_paise: int
    is_idempotent_replay: bool


class CustomerLedgerSummaryResponse(BaseModel):
    """Summary of Udhaar balance for a customer at a specific shop."""
    shop_id: UUID
    shop_name: str
    current_balance_paise: int
    last_entry_sequence: int
    last_transaction_at: Optional[datetime] = None


class GlobalCustomerLedgerSummaryResponse(BaseModel):
    """Aggregated ledger summary across all shops joined by a customer."""
    total_outstanding_paise: int
    shops: List[CustomerLedgerSummaryResponse]


class LedgerHistoryResponse(BaseModel):
    """Paginated or ordered ledger entry history with customer balance."""
    items: List[LedgerEntryResponse]
    total_count: int
    current_balance_paise: int
    last_entry_sequence: int
