import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    decrypt_token,
    encrypt_token,
    generate_qr_svg,
    generate_secure_token,
    hash_token,
)
from app.models.models import Shop, ShopQrAuditLog, ShopRegistrationToken


class QrService:
    @classmethod
    def resolve_registration_base_url(
        cls,
        request: Optional[Request] = None,
        target_override: Optional[str] = None,
    ) -> str:
        """
        Dynamically resolves the reachable base URL for customer registration links:
        1. Explicit target_override (e.g. 'physical', 'emulator', or custom URL)
        2. Client headers if present (X-Client-Device: 'physical'|'emulator', X-Registration-Base-Url)
        3. Host header from incoming request (e.g. 192.168.1.5:8000 or 10.0.2.2:8000)
        4. Centralized settings fallback (effective_registration_base_url)
        """
        if target_override and target_override.strip():
            t = target_override.strip().lower()
            if t in ("physical", "phone", "device"):
                return f"http://{settings.DEV_HOST_IP}:{settings.DEV_PORT}/join"
            elif t == "emulator":
                return f"http://{settings.EMULATOR_HOST}:{settings.DEV_PORT}/join"
            elif t.startswith("http://") or t.startswith("https://"):
                return target_override.rstrip("/")

        if request:
            # Check device header passed by Flutter client
            client_device = request.headers.get("x-client-device")
            if client_device:
                cd = client_device.strip().lower()
                if cd in ("physical", "phone", "device"):
                    return f"http://{settings.DEV_HOST_IP}:{settings.DEV_PORT}/join"
                elif cd == "emulator":
                    return f"http://{settings.EMULATOR_HOST}:{settings.DEV_PORT}/join"

            custom_base = request.headers.get("x-registration-base-url")
            if custom_base:
                return custom_base.rstrip("/")

            # Check query params if available
            try:
                query_target = request.query_params.get("device")
                if query_target:
                    qt = query_target.strip().lower()
                    if qt in ("physical", "phone", "device"):
                        return f"http://{settings.DEV_HOST_IP}:{settings.DEV_PORT}/join"
                    elif qt == "emulator":
                        return f"http://{settings.EMULATOR_HOST}:{settings.DEV_PORT}/join"
            except Exception:
                pass

            # Inspect incoming host header if it is a real network IP / host
            host = request.headers.get("host")
            if host:
                host_lower = host.lower()
                # Ignore test environments so pytest behaves predictably with settings
                if not any(host_lower.startswith(h) for h in ("test", "localhost", "127.0.0.1")):
                    scheme = request.url.scheme or "http"
                    return f"{scheme}://{host}/join"

        return settings.effective_registration_base_url

    @classmethod
    def build_registration_url(
        cls,
        raw_token: str,
        base_url: Optional[str] = None,
        request: Optional[Request] = None,
        target_override: Optional[str] = None,
    ) -> str:
        """Constructs the canonical registration URL."""
        base = base_url or cls.resolve_registration_base_url(request=request, target_override=target_override)
        return f"{base.rstrip('/')}/{raw_token}"

    @classmethod
    async def create_initial_shop_qr(
        cls,
        db: AsyncSession,
        shop_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> ShopRegistrationToken:
        """
        Generates and stores the initial active registration QR token inside an existing transaction.
        Uses AES-256-GCM encryption for token recovery and SHA-256 for public lookup.
        """
        raw_token = generate_secure_token()
        token_hash = hash_token(raw_token)
        encrypted_token = encrypt_token(raw_token)

        token_record = ShopRegistrationToken(
            id=uuid.uuid4(),
            shop_id=shop_id,
            token_hash=token_hash,
            encrypted_token=encrypted_token,
            is_active=True,
        )
        db.add(token_record)

        audit_log = ShopQrAuditLog(
            id=uuid.uuid4(),
            shop_id=shop_id,
            token_id=token_record.id,
            action="GENERATED",
            performed_by_user_id=owner_user_id,
        )
        db.add(audit_log)
        await db.flush()
        return token_record

    @classmethod
    async def get_or_create_active_shop_qr(
        cls,
        db: AsyncSession,
        shop: Shop,
        current_user_id: uuid.UUID,
        request: Optional[Request] = None,
        target_override: Optional[str] = None,
    ) -> Tuple[ShopRegistrationToken, str, str, str]:
        """
        Retrieves the existing static registration QR or creates one if missing.
        Verifies ownership, decrypts the token, and returns:
        (token_record, raw_token, registration_url, qr_svg).
        Preserves existing tokens without rotating or revoking.
        """
        if shop.owner_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to manage this shop's registration QR",
            )

        # Query active token
        query = select(ShopRegistrationToken).where(
            ShopRegistrationToken.shop_id == shop.id,
            ShopRegistrationToken.is_active == True,
        )
        result = await db.execute(query)
        token_record = result.scalar_one_or_none()

        if token_record:
            # Decrypt existing permanent static token
            raw_token = decrypt_token(token_record.encrypted_token)
        else:
            # Generate new token if none exists
            raw_token = generate_secure_token()
            token_hash = hash_token(raw_token)
            encrypted_token = encrypt_token(raw_token)

            token_record = ShopRegistrationToken(
                id=uuid.uuid4(),
                shop_id=shop.id,
                token_hash=token_hash,
                encrypted_token=encrypted_token,
                is_active=True,
            )
            db.add(token_record)

            audit_log = ShopQrAuditLog(
                id=uuid.uuid4(),
                shop_id=shop.id,
                token_id=token_record.id,
                action="GENERATED",
                performed_by_user_id=current_user_id,
            )
            db.add(audit_log)
            await db.commit()
            await db.refresh(token_record)

        reg_url = cls.build_registration_url(
            raw_token, request=request, target_override=target_override
        )
        qr_svg = generate_qr_svg(reg_url)
        return token_record, raw_token, reg_url, qr_svg

    @classmethod
    async def rotate_shop_qr(
        cls,
        db: AsyncSession,
        shop: Shop,
        current_user_id: uuid.UUID,
        request: Optional[Request] = None,
        target_override: Optional[str] = None,
    ) -> Tuple[ShopRegistrationToken, str, str, str]:
        """
        Atomically revokes the current active token and generates a new one.
        Old QR links immediately stop working.
        """
        if shop.owner_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to rotate this shop's registration QR",
            )

        now = datetime.now(timezone.utc)

        # 1. Revoke existing active tokens for this shop
        active_query = select(ShopRegistrationToken).where(
            ShopRegistrationToken.shop_id == shop.id,
            ShopRegistrationToken.is_active == True,
        )
        result = await db.execute(active_query)
        active_tokens = result.scalars().all()
        for t in active_tokens:
            t.is_active = False
            t.revoked_at = now
            t.updated_at = now

        # 2. Generate new cryptographically secure token
        raw_token = generate_secure_token()
        token_hash = hash_token(raw_token)
        encrypted_token = encrypt_token(raw_token)

        new_token = ShopRegistrationToken(
            id=uuid.uuid4(),
            shop_id=shop.id,
            token_hash=token_hash,
            encrypted_token=encrypted_token,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(new_token)

        # 3. Log audit event
        audit_log = ShopQrAuditLog(
            id=uuid.uuid4(),
            shop_id=shop.id,
            token_id=new_token.id,
            action="ROTATED",
            performed_by_user_id=current_user_id,
            created_at=now,
        )
        db.add(audit_log)

        await db.commit()
        await db.refresh(new_token)

        reg_url = cls.build_registration_url(
            raw_token, request=request, target_override=target_override
        )
        qr_svg = generate_qr_svg(reg_url)
        return new_token, raw_token, reg_url, qr_svg

    @classmethod
    async def revoke_shop_qr(
        cls,
        db: AsyncSession,
        shop: Shop,
        current_user_id: uuid.UUID,
    ) -> None:
        """
        Revokes the active registration QR. No replacement token is generated until requested.
        """
        if shop.owner_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to revoke this shop's registration QR",
            )

        now = datetime.now(timezone.utc)
        active_query = select(ShopRegistrationToken).where(
            ShopRegistrationToken.shop_id == shop.id,
            ShopRegistrationToken.is_active == True,
        )
        result = await db.execute(active_query)
        active_tokens = result.scalars().all()

        for t in active_tokens:
            t.is_active = False
            t.revoked_at = now
            t.updated_at = now

            audit_log = ShopQrAuditLog(
                id=uuid.uuid4(),
                shop_id=shop.id,
                token_id=t.id,
                action="REVOKED",
                performed_by_user_id=current_user_id,
                created_at=now,
            )
            db.add(audit_log)

        await db.commit()

    @classmethod
    async def lookup_public_shop_by_token(
        cls,
        db: AsyncSession,
        raw_token: str,
    ) -> Optional[Shop]:
        """
        Performs safe public shop lookup using the SHA-256 hash of the token.
        Returns the associated Shop if active; None if invalid or revoked.
        """
        t_hash = hash_token(raw_token.strip())

        query = (
            select(ShopRegistrationToken)
            .where(
                ShopRegistrationToken.token_hash == t_hash,
                ShopRegistrationToken.is_active == True,
                ShopRegistrationToken.revoked_at == None,
            )
            .options(selectinload(ShopRegistrationToken.shop))
        )
        result = await db.execute(query)
        token_record = result.scalar_one_or_none()

        if not token_record or not token_record.shop:
            return None
        return token_record.shop

