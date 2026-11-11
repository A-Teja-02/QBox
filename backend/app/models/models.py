import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
)
from sqlalchemy.orm import deferred, relationship
from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(32), unique=True, nullable=False, index=True)

    # Relationships
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "role_id"),
    )

    # Relationships
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    phone = Column(String(15), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    shopkeeper_profile = relationship("ShopkeeperProfile", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    customer_profile = relationship("CustomerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    shops = relationship("Shop", back_populates="owner", cascade="all, delete-orphan", lazy="selectin")
    joined_shops = relationship("ShopCustomer", back_populates="customer_user", cascade="all, delete-orphan", lazy="selectin")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    revoked_tokens = relationship("RevokedToken", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    customer_ledger_entries = relationship("LedgerEntry", back_populates="customer_user", foreign_keys="[LedgerEntry.customer_user_id]", cascade="save-update, merge")
    tokens_valid_from = Column(DateTime(timezone=True), nullable=True)

    @property
    def roles(self) -> list[str]:
        return [ur.role.role_name for ur in self.user_roles if ur.role]


class ShopkeeperProfile(Base):
    __tablename__ = "shopkeeper_profiles"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="shopkeeper_profile")


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="customer_profile")


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shop_name = Column(String(255), nullable=False)
    shop_address = Column(Text, nullable=False)
    upi_id = Column(String(255), nullable=True)
    qr_image_path = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    owner = relationship("User", back_populates="shops")
    registration_tokens = relationship("ShopRegistrationToken", back_populates="shop", cascade="all, delete-orphan", lazy="selectin")
    customers = relationship("ShopCustomer", back_populates="shop", cascade="all, delete-orphan", lazy="selectin")
    payment_qrs = relationship("ShopPaymentQr", back_populates="shop", cascade="all, delete-orphan", lazy="selectin")
    ledger_entries = relationship("LedgerEntry", back_populates="shop", foreign_keys="[LedgerEntry.shop_id]", cascade="save-update, merge")


class ShopPaymentQr(Base):
    __tablename__ = "shop_payment_qrs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id = Column(Uuid, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key = Column(String(512), nullable=False, unique=True, index=True)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(64), nullable=False)  # image/png, image/jpeg
    file_size_bytes = Column(Integer, nullable=False)
    file_checksum = Column(String(64), nullable=False)  # SHA-256 hash of bytes
    upi_provider = Column(String(64), nullable=True)  # PhonePe, Google Pay, Paytm, etc.
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    image_data = deferred(Column(LargeBinary, nullable=True))

    __table_args__ = (
        # Partial unique index ensuring at most one active payment QR per shop
        Index(
            "uq_shop_active_payment_qr",
            "shop_id",
            unique=True,
            postgresql_where=Column("is_active") == True,
        ),
    )

    # Relationships
    shop = relationship("Shop", back_populates="payment_qrs")


class ShopRegistrationToken(Base):
    __tablename__ = "shop_registration_tokens"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id = Column(Uuid, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    encrypted_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Partial unique index ensuring at most one active registration token per shop
        Index(
            "uq_shop_active_registration_token",
            "shop_id",
            unique=True,
            postgresql_where=Column("is_active") == True,
        ),
    )

    # Relationships
    shop = relationship("Shop", back_populates="registration_tokens")
    audit_logs = relationship("ShopQrAuditLog", back_populates="token", cascade="all, delete-orphan")


class ShopQrAuditLog(Base):
    __tablename__ = "shop_qr_audit_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id = Column(Uuid, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    token_id = Column(Uuid, ForeignKey("shop_registration_tokens.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # GENERATED, ROTATED, REVOKED
    performed_by_user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    token = relationship("ShopRegistrationToken", back_populates="audit_logs")
    performer = relationship("User")


class ShopCustomer(Base):
    __tablename__ = "shop_customers"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id = Column(Uuid, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="ACTIVE", nullable=False)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    current_balance_paise = deferred(Column(BigInteger, default=0, server_default="0", nullable=False))
    last_entry_sequence = deferred(Column(BigInteger, default=0, server_default="0", nullable=False))

    __table_args__ = (
        UniqueConstraint("shop_id", "customer_user_id", name="uq_shop_customer"),
        CheckConstraint("current_balance_paise >= 0", name="chk_shop_customer_non_negative_balance"),
    )

    # Relationships
    shop = relationship("Shop", back_populates="customers")
    customer_user = relationship("User", back_populates="joined_shops")
    ledger_entries = relationship(
        "LedgerEntry",
        back_populates="shop_customer",
        primaryjoin="and_(ShopCustomer.shop_id == LedgerEntry.shop_id, ShopCustomer.customer_user_id == LedgerEntry.customer_user_id)",
        cascade="save-update, merge",
        overlaps="ledger_entries,customer_ledger_entries",
    )


class LedgerEntry(Base):
    """
    Authoritative Udhaar (credit) and repayment transaction record.
    Immutable: Ledger entries cannot be modified or deleted.
    Monetary amounts are stored as non-negative integers in paise (₹1 = 100 paise).
    """
    __tablename__ = "ledger_entries"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    shop_id = Column(Uuid, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_user_id = Column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id = Column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False)  # 'CREDIT', 'REPAYMENT', 'CREDIT_REVERSAL', 'REPAYMENT_REVERSAL'
    amount_paise = Column(BigInteger, nullable=False)
    note = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=False, index=True)
    original_entry_id = Column(Uuid, ForeignKey("ledger_entries.id", ondelete="RESTRICT"), nullable=True, index=True)
    sequence_number = Column(BigInteger, nullable=False)
    balance_after_transaction_paise = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('CREDIT', 'REPAYMENT', 'CREDIT_REVERSAL', 'REPAYMENT_REVERSAL')",
            name="chk_ledger_transaction_type",
        ),
        CheckConstraint(
            "(transaction_type IN ('CREDIT', 'REPAYMENT') AND original_entry_id IS NULL) OR "
            "(transaction_type IN ('CREDIT_REVERSAL', 'REPAYMENT_REVERSAL') AND original_entry_id IS NOT NULL)",
            name="chk_ledger_reversal_original_entry",
        ),
        CheckConstraint(
            "amount_paise > 0",
            name="chk_ledger_positive_amount",
        ),
        UniqueConstraint(
            "shop_id", "idempotency_key",
            name="uq_ledger_shop_idempotency_key",
        ),
        UniqueConstraint(
            "shop_id", "customer_user_id", "sequence_number",
            name="uq_ledger_customer_sequence",
        ),
        ForeignKeyConstraint(
            ["shop_id", "customer_user_id"],
            ["shop_customers.shop_id", "shop_customers.customer_user_id"],
            name="fk_ledger_shop_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["original_entry_id"],
            ["ledger_entries.id"],
            name="fk_ledger_entries_original_entry_id",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_ledger_shop_customer_created",
            "shop_id", "customer_user_id", "created_at",
        ),
        Index(
            "ix_ledger_shop_created",
            "shop_id", "created_at",
        ),
        Index(
            "ix_ledger_customer_created",
            "customer_user_id", "created_at",
        ),
    )

    # Relationships
    shop = relationship("Shop", foreign_keys=[shop_id], back_populates="ledger_entries", overlaps="ledger_entries")
    customer_user = relationship("User", foreign_keys=[customer_user_id], back_populates="customer_ledger_entries", overlaps="customer_ledger_entries,ledger_entries")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    shop_customer = relationship(
        "ShopCustomer",
        back_populates="ledger_entries",
        primaryjoin="and_(LedgerEntry.shop_id == ShopCustomer.shop_id, LedgerEntry.customer_user_id == ShopCustomer.customer_user_id)",
        overlaps="customer_ledger_entries,customer_user,ledger_entries,shop",
    )
    original_entry = relationship("LedgerEntry", remote_side=[id], back_populates="reversals")
    reversals = relationship("LedgerEntry", back_populates="original_entry", cascade="save-update, merge")


class RateLimitEvent(Base):
    """PostgreSQL-backed shared rate limiter table for multi-worker and multi-instance deployments."""
    __tablename__ = "rate_limit_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    key = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class RefreshToken(Base):
    """
    PostgreSQL-backed session storage for Refresh Tokens.
    Supports Refresh Token Rotation (RTR), family revocation, and replay attack detection.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(64), unique=True, nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    family_id = Column(Uuid, nullable=False, index=True)
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class RevokedToken(Base):
    """
    PostgreSQL-backed blacklist of revoked tokens (access and refresh tokens).
    Ensures that when a user logs out, the access token is immediately rejected with HTTP 401
    across all protected endpoints, without waiting for natural JWT expiration.
    """
    __tablename__ = "revoked_tokens"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    token_jti = Column(String(64), unique=True, nullable=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_type = Column(String(16), default="access", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="revoked_tokens")
