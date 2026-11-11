import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    clear_failed_attempts,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    is_rate_limited,
    record_failed_attempt,
    verify_password,
)
from app.models.models import (
    CustomerProfile,
    RefreshToken,
    RevokedToken,
    Role,
    Shop,
    ShopkeeperProfile,
    ShopPaymentQr,
    User,
    UserRole,
)
from app.schemas.auth import (
    CustomerRegisterRequest,
    LoginRequest,
    LogoutRequest,
    ShopkeeperRegisterRequest,
    ShopkeeperRegisterResponse,
    TokenResponse,
    UserProfileResponse,
    normalize_email_address,
    normalize_phone_number,
)


class AuthService:
    @staticmethod
    async def get_or_create_role(db: AsyncSession, role_name: str) -> Role:
        """Retrieves an existing role or creates it if missing."""
        result = await db.execute(select(Role).where(Role.role_name == role_name))
        role = result.scalar_one_or_none()
        if not role:
            role = Role(role_name=role_name)
            db.add(role)
            await db.flush()
        return role

    @classmethod
    async def create_user_refresh_session(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        family_id: Optional[uuid.UUID] = None,
    ) -> Tuple[str, RefreshToken]:
        """
        Creates a cryptographically signed refresh token and persists the session in PostgreSQL.
        Supports token families for rotation tracking and reuse detection.
        """
        family = family_id or uuid.uuid4()
        token_jti = str(uuid.uuid4())

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        raw_refresh_token = create_refresh_token({
            "sub": str(user_id),
            "jti": token_jti,
            "family": str(family),
        })

        token_digest = hash_token(raw_refresh_token)

        record = RefreshToken(
            user_id=user_id,
            token_jti=token_jti,
            token_hash=token_digest,
            family_id=family,
            is_revoked=False,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(record)
        return raw_refresh_token, record

    @classmethod
    async def register_shopkeeper(
        cls,
        db: AsyncSession,
        req: ShopkeeperRegisterRequest,
        payment_qr_file: Optional[Tuple[bytes, str]] = None,
    ) -> ShopkeeperRegisterResponse:
        """
        Registers a new shopkeeper or attaches the SHOPKEEPER role to an existing user.
        Executes within an atomic transaction.
        """
        phone = req.phone
        email = req.email

        # 1. Check if user with this phone already exists
        user_query = select(User).where(User.phone == phone).options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.shopkeeper_profile),
            selectinload(User.shops),
        )
        result = await db.execute(user_query)
        existing_user = result.scalar_one_or_none()

        # 2. Check email uniqueness if email provided
        if email:
            email_query = select(User).where(User.email == email)
            email_res = await db.execute(email_query)
            email_user = email_res.scalar_one_or_none()
            if email_user and (not existing_user or email_user.id != existing_user.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address is already registered with another account",
                )

        # 3. Retrieve or create the SHOPKEEPER role
        shopkeeper_role = await cls.get_or_create_role(db, "SHOPKEEPER")

        if existing_user:
            # Check if user is already a shopkeeper
            if "SHOPKEEPER" in existing_user.roles:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Mobile number is already registered as a shopkeeper",
                )

            # User exists as Customer - attach SHOPKEEPER role and shopkeeper profile
            user = existing_user
            user_role = UserRole(user_id=user.id, role_id=shopkeeper_role.id)
            db.add(user_role)
            roles = list(set(existing_user.roles + ["SHOPKEEPER"]))
        else:
            # Create new user account with Argon2id hashed password
            hashed_pw = hash_password(req.password)
            user = User(
                phone=phone,
                email=email,
                password_hash=hashed_pw,
                is_active=True,
            )
            db.add(user)
            await db.flush()  # assign user.id

            user_role = UserRole(user_id=user.id, role_id=shopkeeper_role.id)
            db.add(user_role)
            roles = ["SHOPKEEPER"]

        # 4. Create Shopkeeper Profile
        shopkeeper_profile = ShopkeeperProfile(
            user_id=user.id,
            full_name=req.full_name,
        )
        db.add(shopkeeper_profile)

        # 5. Create Shop entity
        shop = Shop(
            owner_user_id=user.id,
            shop_name=req.shop_name,
            shop_address=req.shop_address,
            upi_id=req.upi_id,
            qr_image_path=req.qr_image_path,
        )
        db.add(shop)
        await db.flush()  # assign shop.id

        # 6. Save Payment QR if provided
        saved_storage_key: Optional[str] = None
        payment_qr_record: Optional[ShopPaymentQr] = None

        payment_qr_bytes: Optional[bytes] = None
        payment_qr_filename = "payment_qr.png"

        if payment_qr_file:
            payment_qr_bytes, payment_qr_filename = payment_qr_file
        elif req.payment_qr_base64:
            import base64
            try:
                payment_qr_bytes = base64.b64decode(req.payment_qr_base64)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid base64 payload for payment QR image.",
                )

        try:
            if payment_qr_bytes:
                from app.services.storage_service import StorageService
                qr_meta = StorageService.save_payment_qr(
                    shop_id=shop.id,
                    file_bytes=payment_qr_bytes,
                    original_filename=payment_qr_filename,
                )
                saved_storage_key = qr_meta["storage_key"]

                # Auto-populate detected UPI ID if not manually entered
                if not shop.upi_id and qr_meta.get("detected_upi_id"):
                    shop.upi_id = qr_meta["detected_upi_id"]

                payment_qr_record = ShopPaymentQr(
                    id=uuid.uuid4(),
                    shop_id=shop.id,
                    storage_key=qr_meta["storage_key"],
                    original_filename=qr_meta["original_filename"],
                    content_type=qr_meta["content_type"],
                    file_size_bytes=qr_meta["file_size_bytes"],
                    file_checksum=qr_meta["file_checksum"],
                    upi_provider=qr_meta["upi_provider"],
                    is_active=True,
                    image_data=payment_qr_bytes,
                )
                db.add(payment_qr_record)
                shop.qr_image_path = f"/api/v1/shops/{shop.id}/payment-qr/image"

            # 7. Automatically generate the initial permanent registration QR code atomically
            from app.services.qr_service import QrService
            await QrService.create_initial_shop_qr(db, shop.id, user.id)

            # 8. Generate immediate authentication tokens and persist refresh session
            access_token = create_access_token({"sub": str(user.id), "phone": user.phone, "roles": roles})
            refresh_token, _ = await cls.create_user_refresh_session(db, user.id)

            # Commit transaction atomically
            await db.commit()

        except Exception:
            await db.rollback()
            raise

        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            roles=roles,
            user_id=str(user.id),
            phone=user.phone,
            full_name=req.full_name,
            shop_id=shop.id,
            shop_name=shop.shop_name,
            shop_address=shop.shop_address,
        )

        payment_qr_url = f"/api/v1/shops/{shop.id}/payment-qr/image" if payment_qr_record else None

        return ShopkeeperRegisterResponse(
            user_id=user.id,
            phone=user.phone,
            email=user.email,
            full_name=req.full_name,
            shop_id=shop.id,
            shop_name=shop.shop_name,
            shop_address=shop.shop_address,
            upi_id=shop.upi_id,
            qr_image_path=shop.qr_image_path,
            roles=roles,
            created_at=user.created_at,
            tokens=token_response,
            payment_qr_url=payment_qr_url,
            payment_qr_id=payment_qr_record.id if payment_qr_record else None,
            has_payment_qr=payment_qr_record is not None,
        )

    @classmethod
    async def register_customer(
        cls,
        db: AsyncSession,
        req: CustomerRegisterRequest,
    ) -> TokenResponse:
        """
        Registers a new customer account or attaches CUSTOMER role to an existing user account.
        Atomically hashes password with Argon2id and commits.
        """
        phone = req.phone

        user_query = select(User).where(User.phone == phone).options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.customer_profile),
            selectinload(User.shopkeeper_profile),
            selectinload(User.shops),
        )
        res = await db.execute(user_query)
        existing_user = res.scalar_one_or_none()

        customer_role = await cls.get_or_create_role(db, "CUSTOMER")

        if existing_user:
            if "CUSTOMER" in existing_user.roles:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Mobile number is already registered as a customer",
                )
            user = existing_user
            user_role = UserRole(user_id=user.id, role_id=customer_role.id)
            db.add(user_role)
            roles = list(set(existing_user.roles + ["CUSTOMER"]))
        else:
            hashed_pw = hash_password(req.password)
            user = User(
                phone=phone,
                password_hash=hashed_pw,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            user_role = UserRole(user_id=user.id, role_id=customer_role.id)
            db.add(user_role)
            roles = ["CUSTOMER"]

        cust_profile = CustomerProfile(
            user_id=user.id,
            full_name=req.full_name,
            address=req.address,
        )
        db.add(cust_profile)

        access_token = create_access_token({"sub": str(user.id), "phone": user.phone, "roles": roles})
        refresh_token, _ = await cls.create_user_refresh_session(db, user.id)

        await db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            roles=roles,
            user_id=str(user.id),
            phone=user.phone,
            full_name=req.full_name,
        )

    @classmethod
    async def login(cls, db: AsyncSession, req: LoginRequest) -> TokenResponse:
        """
        Authenticates a user via phone or email and password.
        Implements rate limiting and anti-enumeration generic error messages.
        """
        raw_identifier = req.identifier.strip()

        # Check brute force rate limit
        if is_rate_limited(raw_identifier):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again in 15 minutes.",
            )

        # Determine if identifier is an email or phone number
        is_email = "@" in raw_identifier
        normalized_phone = None
        normalized_email = None

        if is_email:
            try:
                normalized_email = normalize_email_address(raw_identifier)
            except ValueError:
                normalized_email = raw_identifier.lower()
        else:
            try:
                normalized_phone = normalize_phone_number(raw_identifier)
            except ValueError:
                normalized_phone = raw_identifier

        # Query user
        query = select(User).options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.shopkeeper_profile),
            selectinload(User.shops),
        )

        if is_email:
            query = query.where(User.email == normalized_email)
        else:
            query = query.where(User.phone == normalized_phone)

        result = await db.execute(query)
        user = result.scalar_one_or_none()

        # Safe error if user not found or password mismatch
        if not user or not verify_password(req.password, user.password_hash):
            record_failed_attempt(raw_identifier)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid mobile number/email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been deactivated.",
            )

        # Clear failed attempts on successful authentication
        clear_failed_attempts(raw_identifier)

        roles = user.roles
        access_token = create_access_token({"sub": str(user.id), "phone": user.phone, "roles": roles})
        refresh_token, _ = await cls.create_user_refresh_session(db, user.id)
        await db.commit()

        full_name = user.shopkeeper_profile.full_name if user.shopkeeper_profile else None
        shop = user.shops[0] if user.shops else None
        shop_id = shop.id if shop else None
        shop_name = shop.shop_name if shop else None
        shop_address = shop.shop_address if shop else None

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            roles=roles,
            user_id=str(user.id),
            phone=user.phone,
            full_name=full_name,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_address=shop_address,
        )

    @classmethod
    async def refresh_access_token(cls, db: AsyncSession, refresh_token: str) -> TokenResponse:
        """
        Validates a refresh token against PostgreSQL, checks expiration, enforces
        Refresh Token Rotation (RTR), detects token reuse (replay attacks), and issues fresh tokens.
        """
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh" or not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_jti = payload.get("jti")
        if not token_jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token claims: missing token identifier.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            user_id = uuid.UUID(payload["sub"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token identity.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Look up refresh token in database
        res = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == token_jti))
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        # Detect reuse or invalid token
        if not record or record.is_revoked:
            if record and record.is_revoked:
                # Security alert: An already revoked token was presented again!
                # Invalidate all tokens in this family to protect against stolen tokens.
                await db.execute(
                    update(RefreshToken)
                    .where(RefreshToken.family_id == record.family_id)
                    .values(is_revoked=True, revoked_at=now)
                )
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Revoked refresh token presented. Potential token reuse detected. All sessions in this chain have been terminated.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unrecognized refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check token expiration
        if record.expires_at < now:
            record.is_revoked = True
            record.revoked_at = now
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Retrieve user
        query = select(User).where(User.id == user_id).options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.shopkeeper_profile),
            selectinload(User.shops),
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 1. Invalidate currently used refresh token (Rotation)
        record.is_revoked = True
        record.revoked_at = now

        # 2. Issue new access token
        roles = user.roles
        access_token = create_access_token({"sub": str(user.id), "phone": user.phone, "roles": roles})

        # 3. Issue new rotated refresh token in the same session family
        new_refresh_token, _ = await cls.create_user_refresh_session(
            db=db,
            user_id=user.id,
            family_id=record.family_id,
        )

        await db.commit()

        full_name = user.shopkeeper_profile.full_name if user.shopkeeper_profile else None
        shop = user.shops[0] if user.shops else None
        shop_id = shop.id if shop else None
        shop_name = shop.shop_name if shop else None
        shop_address = shop.shop_address if shop else None

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            roles=roles,
            user_id=str(user.id),
            phone=user.phone,
            full_name=full_name,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_address=shop_address,
        )

    @classmethod
    async def logout(
        cls,
        db: AsyncSession,
        current_user: User,
        raw_access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        all_sessions: bool = False,
    ) -> dict:
        """
        Invalidates user authentication session server-side.
        1. Immediately revokes the presented access token so subsequent calls receive HTTP 401.
        2. Revokes refresh token sessions in PostgreSQL (either single family or all user sessions).
        3. If all_sessions is True, updates current_user.tokens_valid_from to invalidate all prior tokens.
        """
        now = datetime.now(timezone.utc)
        revoked_count = 0

        # 1. Immediately revoke the presented access token
        if raw_access_token:
            payload = decode_token(raw_access_token)
            if payload:
                jti = payload.get("jti")
                exp_ts = payload.get("exp")
                expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else (now + timedelta(hours=1))
                token_hash = hash_token(raw_access_token)

                revoked_record = RevokedToken(
                    id=uuid.uuid4(),
                    token_jti=jti,
                    token_hash=token_hash,
                    user_id=current_user.id,
                    token_type="access",
                    expires_at=expires_at,
                    revoked_at=now,
                )
                db.add(revoked_record)

        # 2. Invalidate refresh token session(s)
        if all_sessions:
            current_user.tokens_valid_from = now
            db.add(current_user)
            res = await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)
                .values(is_revoked=True, revoked_at=now)
            )
            revoked_count = res.rowcount
        elif refresh_token:
            payload = decode_token(refresh_token)
            if payload and payload.get("jti"):
                jti = payload["jti"]
                res = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == jti))
                record = res.scalar_one_or_none()
                if record:
                    await db.execute(
                        update(RefreshToken)
                        .where(RefreshToken.family_id == record.family_id, RefreshToken.is_revoked == False)
                        .values(is_revoked=True, revoked_at=now)
                    )
                    revoked_count += 1
                else:
                    # Token not in DB or already revoked
                    revoked_count = 0
        else:
            # Revoke all active sessions for current user
            res = await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)
                .values(is_revoked=True, revoked_at=now)
            )
            revoked_count = res.rowcount

        await db.commit()
        return {
            "status": "logged_out",
            "message": "User session has been revoked server-side.",
            "revoked_sessions": revoked_count,
        }

    @classmethod
    async def get_current_user_profile(cls, db: AsyncSession, user_id: uuid.UUID) -> UserProfileResponse:
        """Retrieves the safe user profile."""
        query = select(User).where(User.id == user_id).options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.shopkeeper_profile),
            selectinload(User.shops),
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        full_name = user.shopkeeper_profile.full_name if user.shopkeeper_profile else None
        shop = user.shops[0] if user.shops else None
        shop_id = shop.id if shop else None
        shop_name = shop.shop_name if shop else None
        shop_address = shop.shop_address if shop else None

        return UserProfileResponse(
            user_id=user.id,
            phone=user.phone,
            email=user.email,
            roles=user.roles,
            full_name=full_name,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_address=shop_address,
            created_at=user.created_at,
        )

