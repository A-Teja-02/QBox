import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Role, Shop, ShopkeeperProfile, User, UserRole


@pytest.fixture(autouse=True)
async def cleanup_test_data(db_session: AsyncSession):
    """Ensure test phone records do not conflict between test runs."""
    await db_session.execute(
        text("DELETE FROM users WHERE phone IN ('+919876500001', '+919876500002', '+919876500003')")
    )
    await db_session.commit()
    yield
    # Cleanup after test session as well
    await db_session.execute(
        text("DELETE FROM users WHERE phone IN ('+919876500001', '+919876500002', '+919876500003')")
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_01_postgres_connectivity(db_session: AsyncSession):
    """Confirm live PostgreSQL database connectivity and version."""
    result = await db_session.execute(text("SELECT 1 as connected, current_database(), current_user"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] in ("qbox_db", "qbox_test_db")
    assert row[2] == "qbox_app"


@pytest.mark.asyncio
async def test_02_successful_shopkeeper_registration(client: AsyncClient, db_session: AsyncSession):
    """Test full shopkeeper registration and confirm database records."""
    unique_phone = "9876500001"
    unique_email = "ramesh.store@example.com"

    payload = {
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road, Bengaluru",
        "phone": unique_phone,
        "email": unique_email,
        "password": "SecurePassword@123",
        "upi_id": "chandrakirana@upi",
        "qr_image_path": "bhim_store_standee_qr.png",
    }

    response = await client.post("/api/v1/auth/register/shopkeeper", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    # Response verification
    assert data["phone"] == "+919876500001"
    assert data["email"] == unique_email
    assert data["full_name"] == "Ramesh Chandra"
    assert data["shop_name"] == "Chandra Kirana"
    assert "password" not in data
    assert "password_hash" not in data
    assert "SHOPKEEPER" in data["roles"]
    assert "tokens" in data
    assert "access_token" in data["tokens"]

    user_id = uuid.UUID(data["user_id"])

    # Confirm record directly in PostgreSQL
    user_query = select(User).where(User.id == user_id).options(
        selectinload(User.shopkeeper_profile),
        selectinload(User.shops),
        selectinload(User.user_roles).selectinload(UserRole.role),
    )
    result = await db_session.execute(user_query)
    user = result.scalar_one_or_none()

    assert user is not None
    assert user.phone == "+919876500001"
    assert user.email == unique_email
    # Confirm password hash is Argon2id
    assert user.password_hash.startswith("$argon2id$")
    assert "SecurePassword@123" not in user.password_hash

    # Confirm Shopkeeper Profile in PostgreSQL
    assert user.shopkeeper_profile is not None
    assert user.shopkeeper_profile.full_name == "Ramesh Chandra"

    # Confirm Shop linked to user in PostgreSQL
    assert len(user.shops) >= 1
    shop = user.shops[0]
    assert shop.owner_user_id == user.id
    assert shop.shop_name == "Chandra Kirana"
    assert shop.shop_address == "Shop 12, Market Main Road, Bengaluru"
    assert shop.upi_id == "chandrakirana@upi"


@pytest.mark.asyncio
async def test_03_duplicate_mobile_number_rejection(client: AsyncClient):
    """Test duplicate registration with the same phone number is rejected."""
    # First registration
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    # Duplicate registration
    payload = {
        "full_name": "Duplicate Tester",
        "shop_name": "Duplicate Store",
        "shop_address": "Shop 99, Market Road",
        "phone": "+91 98765 00001",  # Same phone formatted differently
        "email": "another.email@example.com",
        "password": "AnotherPassword@123",
    }

    response = await client.post("/api/v1/auth/register/shopkeeper", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert "already registered" in data["detail"].lower()


@pytest.mark.asyncio
async def test_04_duplicate_email_rejection(client: AsyncClient):
    """Test duplicate registration with the same email is rejected."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "First User",
        "shop_name": "First Store",
        "shop_address": "Shop 1, Market Road",
        "phone": "9876500001",
        "email": "unique.shop@example.com",
        "password": "SecurePassword@123",
    })

    payload = {
        "full_name": "Different Phone User",
        "shop_name": "Different Store",
        "shop_address": "Shop 100, Market Road",
        "phone": "9876500002",  # Different phone
        "email": "UNIQUE.SHOP@EXAMPLE.COM",  # Same email uppercase
        "password": "AnotherPassword@123",
    }

    response = await client.post("/api/v1/auth/register/shopkeeper", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert "email address is already registered" in data["detail"].lower()


@pytest.mark.asyncio
async def test_05_successful_login_with_phone(client: AsyncClient):
    """Test logging in using normalized mobile number and password."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    payload = {
        "identifier": "98765 00001",
        "password": "SecurePassword@123",
    }

    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["phone"] == "+919876500001"
    assert "SHOPKEEPER" in data["roles"]
    assert data["shop_name"] == "Chandra Kirana"
    assert data["shop_id"] is not None
    assert data["shop_address"] == "Shop 12, Market Main Road"


@pytest.mark.asyncio
async def test_06_successful_login_with_email(client: AsyncClient):
    """Test logging in using email address and password."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "email": "ramesh.store@example.com",
        "password": "SecurePassword@123",
    })

    payload = {
        "identifier": "Ramesh.Store@example.com",
        "password": "SecurePassword@123",
    }

    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["phone"] == "+919876500001"
    assert "SHOPKEEPER" in data["roles"]


@pytest.mark.asyncio
async def test_07_incorrect_password_rejection(client: AsyncClient):
    """Test login rejection on incorrect password (anti-enumeration generic message)."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    payload = {
        "identifier": "9876500001",
        "password": "WrongPassword123",
    }

    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Invalid mobile number/email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_08_authenticated_me_endpoint(client: AsyncClient):
    """Test protected /auth/me endpoint using JWT Bearer token."""
    reg_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })
    token = reg_res.json()["tokens"]["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "+919876500001"
    assert data["full_name"] == "Ramesh Chandra"
    assert "SHOPKEEPER" in data["roles"]


@pytest.mark.asyncio
async def test_09_multiple_roles_support(client: AsyncClient, db_session: AsyncSession):
    """Test attaching CUSTOMER role to the same user without creating duplicate account."""
    reg_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Multi Role User",
        "shop_name": "Multi Store",
        "shop_address": "Market Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })
    user_id = uuid.UUID(reg_res.json()["user_id"])

    # Retrieve CUSTOMER role
    customer_role_res = await db_session.execute(select(Role).where(Role.role_name == "CUSTOMER"))
    customer_role = customer_role_res.scalar_one()

    # Attach CUSTOMER role to the existing user
    user_role = UserRole(user_id=user_id, role_id=customer_role.id)
    db_session.add(user_role)
    await db_session.commit()

    # Re-login and confirm both roles returned
    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "+919876500001",
        "password": "SecurePassword@123",
    })
    assert login_res.status_code == 200
    roles = login_res.json()["roles"]
    assert "SHOPKEEPER" in roles
    assert "CUSTOMER" in roles


@pytest.mark.asyncio
async def test_10_token_refresh_flow(client: AsyncClient):
    """Test refreshing an access token using a valid refresh token."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500001",
        "password": "SecurePassword@123",
    })
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    refreshed_data = refresh_res.json()
    assert "access_token" in refreshed_data
    assert refreshed_data["shop_id"] == login_res.json()["shop_id"]

    # Reject invalid refresh token
    bad_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid-token"})
    assert bad_res.status_code == 401


@pytest.mark.asyncio
async def test_11_refresh_token_rotation_and_reuse_detection(client: AsyncClient):
    """Confirm Refresh Token Rotation (RTR) and replay/reuse attack family invalidation."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500001",
        "password": "SecurePassword@123",
    })
    token_1 = login_res.json()["refresh_token"]

    # First rotation: token_1 -> token_2
    res_rot_1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert res_rot_1.status_code == 200
    token_2 = res_rot_1.json()["refresh_token"]
    assert token_2 != token_1

    # Second rotation: token_2 -> token_3
    res_rot_2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": token_2})
    assert res_rot_2.status_code == 200
    token_3 = res_rot_2.json()["refresh_token"]
    assert token_3 != token_2

    # Attempt to reuse old token_1 (replay attack!)
    reuse_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert reuse_res.status_code == 401
    assert "token reuse" in reuse_res.json()["detail"].lower()

    # The entire family must now be revoked; token_3 should also be rejected
    token_3_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": token_3})
    assert token_3_res.status_code == 401


@pytest.mark.asyncio
async def test_12_refresh_token_rejected_on_access_token_endpoints(client: AsyncClient):
    """Ensure refresh tokens cannot be spoofed as access tokens on protected endpoints."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500001",
        "password": "SecurePassword@123",
    })
    refresh_token = login_res.json()["refresh_token"]

    # Attempt to access /api/v1/auth/me using refresh token as Bearer auth
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert me_res.status_code == 401
    assert "access token is required" in me_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_13_server_side_logout_invalidates_session(client: AsyncClient):
    """Ensure logout revokes refresh tokens in the database."""
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 12, Market Main Road",
        "phone": "9876500001",
        "password": "SecurePassword@123",
    })

    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500001",
        "password": "SecurePassword@123",
    })
    access_token = login_res.json()["access_token"]
    refresh_token = login_res.json()["refresh_token"]

    # Logout
    logout_res = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # Subsequent refresh attempt with revoked token must fail
    refresh_after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_14_access_token_immediately_rejected_after_logout(client: AsyncClient):
    """
    Requirement 1: After logout, verify that the previously issued access token
    immediately receives HTTP 401 on protected endpoints, not merely that its refresh token is revoked.
    """
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 14, Market Road",
        "phone": "9876500014",
        "password": "SecurePassword@123",
    })

    login_res = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500014",
        "password": "SecurePassword@123",
    })
    access_token = login_res.json()["access_token"]
    refresh_token = login_res.json()["refresh_token"]

    # 1. Before logout: access token succeeds on protected endpoints
    me_before = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_before.status_code == 200

    qr_before = await client.get("/api/v1/shops/me/registration-qr", headers={"Authorization": f"Bearer {access_token}"})
    assert qr_before.status_code == 200

    # 2. Perform logout
    logout_res = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # 3. Immediately after logout: the previous access token MUST receive HTTP 401
    me_after = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_after.status_code == 401
    assert "revoked" in me_after.json()["detail"].lower()

    qr_after = await client.get("/api/v1/shops/me/registration-qr", headers={"Authorization": f"Bearer {access_token}"})
    assert qr_after.status_code == 401
    assert "revoked" in qr_after.json()["detail"].lower()

    rotate_after = await client.post("/api/v1/shops/me/registration-qr/rotate", headers={"Authorization": f"Bearer {access_token}"})
    assert rotate_after.status_code == 401
    assert "revoked" in rotate_after.json()["detail"].lower()


@pytest.mark.asyncio
async def test_15_all_sessions_logout_invalidates_all_prior_access_tokens(client: AsyncClient):
    """
    Ensure all_sessions=True invalidates all prior access tokens for the user account.
    """
    await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Ramesh Chandra",
        "shop_name": "Chandra Kirana",
        "shop_address": "Shop 15, Market Road",
        "phone": "9876500015",
        "password": "SecurePassword@123",
    })

    # Device A login
    login_a = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500015",
        "password": "SecurePassword@123",
    })
    token_a = login_a.json()["access_token"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})).status_code == 200

    # Device B login
    login_b = await client.post("/api/v1/auth/login", json={
        "identifier": "9876500015",
        "password": "SecurePassword@123",
    })
    token_b = login_b.json()["access_token"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})).status_code == 200

    # Device B calls logout with all_sessions=True
    logout_res = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"all_sessions": True},
    )
    assert logout_res.status_code == 200

    # Both tokens must now be rejected with 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})).status_code == 401
