import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token, hash_token
from app.db.session import get_db
from app.models.models import RevokedToken, Shop, User, UserRole

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticates the incoming request via JWT Bearer token and validates active session."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    payload = decode_token(raw_token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Immediate revocation check: verify this token was not revoked upon logout
    token_hash = hash_token(raw_token)
    jti = payload.get("jti")
    revocation_stmt = select(RevokedToken.id).where(
        or_(
            RevokedToken.token_hash == token_hash,
            RevokedToken.token_jti == jti if jti else False,
        )
    ).limit(1)
    revoked_res = await db.execute(revocation_stmt)
    if revoked_res.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token identity.")

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

    # 2. Check if all user tokens were revoked after this token was issued (e.g. global logout)
    if user.tokens_valid_from:
        iat = payload.get("iat")
        if iat is not None:
            token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
            if token_issued_at < user.tokens_valid_from:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication token has been revoked. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    return user


def require_role(required_role: str):
    """Enforces role-based authorization for protected routes."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if required_role not in current_user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {required_role} role is required.",
            )
        return current_user
    return role_checker


async def get_shop_by_id(shop_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Shop:
    """Retrieves a Shop by its UUID or raises a 404."""
    query = select(Shop).where(Shop.id == shop_id)
    result = await db.execute(query)
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found.",
        )
    return shop


