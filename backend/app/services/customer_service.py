import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.models.models import CustomerProfile, Role, Shop, ShopCustomer, User, UserRole
from app.services.auth_service import AuthService
from app.services.qr_service import QrService


class CustomerService:
    @classmethod
    async def join_shop_via_token(
        cls,
        db: AsyncSession,
        customer_user: User,
        shop_id: uuid.UUID,
        raw_token: str,
    ) -> Dict[str, Any]:
        """
        Idempotently joins an authenticated customer to a shop using a scanned registration token.
        Ensures the customer relationship is created without any financial/Udhaar transactions.
        """
        # 1. Validate that the token matches the shop and is active
        shop = await QrService.lookup_public_shop_by_token(db, raw_token)
        if not shop or shop.id != shop_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration QR code is invalid or has expired.",
            )

        # 2. Check if the customer has already joined this shop
        existing_query = select(ShopCustomer).where(
            ShopCustomer.shop_id == shop_id,
            ShopCustomer.customer_user_id == customer_user.id,
        )
        res = await db.execute(existing_query)
        existing_link = res.scalar_one_or_none()

        if existing_link:
            return {
                "status": "already_joined",
                "shop_id": str(shop.id),
                "shop_name": shop.shop_name,
                "shop_address": shop.shop_address,
                "joined_at": existing_link.joined_at,
            }

        now = datetime.now(timezone.utc)

        # 3. Create the ShopCustomer association
        new_link = ShopCustomer(
            id=uuid.uuid4(),
            shop_id=shop.id,
            customer_user_id=customer_user.id,
            status="ACTIVE",
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(new_link)

        # 4. Ensure customer has the CUSTOMER role
        if "CUSTOMER" not in customer_user.roles:
            customer_role = await AuthService.get_or_create_role(db, "CUSTOMER")
            user_role = UserRole(user_id=customer_user.id, role_id=customer_role.id)
            db.add(user_role)

        # 5. Ensure customer has a customer profile record if missing
        profile_query = select(CustomerProfile).where(CustomerProfile.user_id == customer_user.id)
        prof_res = await db.execute(profile_query)
        if not prof_res.scalar_one_or_none():
            # Use full name from shopkeeper profile or phone as fallback
            name_fallback = customer_user.phone
            if customer_user.shopkeeper_profile:
                name_fallback = customer_user.shopkeeper_profile.full_name
            cust_profile = CustomerProfile(
                id=uuid.uuid4(),
                user_id=customer_user.id,
                full_name=name_fallback,
                created_at=now,
                updated_at=now,
            )
            db.add(cust_profile)

        await db.commit()

        return {
            "status": "joined",
            "shop_id": str(shop.id),
            "shop_name": shop.shop_name,
            "shop_address": shop.shop_address,
            "joined_at": now,
        }

    @classmethod
    async def get_customer_joined_shops(
        cls,
        db: AsyncSession,
        customer_user_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Retrieves all shops joined by a customer."""
        query = (
            select(ShopCustomer)
            .where(
                ShopCustomer.customer_user_id == customer_user_id,
                ShopCustomer.status == "ACTIVE",
            )
            .options(selectinload(ShopCustomer.shop))
            .order_by(ShopCustomer.joined_at.desc())
        )
        result = await db.execute(query)
        links = result.scalars().all()

        return [
            {
                "shop_id": str(link.shop.id),
                "shop_name": link.shop.shop_name,
                "shop_address": link.shop.shop_address,
                "upi_id": link.shop.upi_id,
                "joined_at": link.joined_at,
            }
            for link in links
            if link.shop
        ]

    @classmethod
    async def get_shop_customers(
        cls,
        db: AsyncSession,
        shop: Shop,
        current_user_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all customers registered with a shopkeeper's shop.
        Enforces tenant isolation by verifying ownership.
        """
        if shop.owner_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view customers of this shop",
            )

        query = (
            select(ShopCustomer)
            .where(
                ShopCustomer.shop_id == shop.id,
                ShopCustomer.status == "ACTIVE",
            )
            .options(
                undefer(ShopCustomer.current_balance_paise),
                selectinload(ShopCustomer.customer_user).selectinload(User.customer_profile),
                selectinload(ShopCustomer.customer_user).selectinload(User.shopkeeper_profile),
            )
            .order_by(ShopCustomer.joined_at.desc())
        )
        result = await db.execute(query)
        links = result.scalars().all()

        customers = []
        for link in links:
            user = link.customer_user
            name = "Customer"
            if user.customer_profile and user.customer_profile.full_name:
                name = user.customer_profile.full_name
            elif user.shopkeeper_profile and user.shopkeeper_profile.full_name:
                name = user.shopkeeper_profile.full_name

            customers.append({
                "customer_user_id": str(user.id),
                "full_name": name,
                "phone": user.phone,
                "joined_at": link.joined_at,
                "current_balance_paise": link.current_balance_paise or 0,
            })

        return customers

