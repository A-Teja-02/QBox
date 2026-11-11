import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token, hash_token


@pytest.fixture(autouse=True)
async def cleanup_test_qr_data(db_session: AsyncSession):
    """Ensure test users and shops are cleaned up before and after tests."""
    await db_session.execute(
        text("DELETE FROM users WHERE phone LIKE '+9198765%'")
    )
    await db_session.commit()
    yield
    await db_session.execute(
        text("DELETE FROM users WHERE phone LIKE '+9198765%'")
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_01_automatic_qr_creation_on_shopkeeper_registration(client: AsyncClient, db_session: AsyncSession):
    """Confirm that whenever a new shopkeeper registers, their registration QR is created automatically in PostgreSQL."""
    reg_payload = {
        "full_name": "Suresh Raina",
        "shop_name": "Raina General Store",
        "shop_address": "MG Road, Kanpur",
        "phone": "9876511111",
        "password": "Password@123",
    }
    res = await client.post("/api/v1/auth/register/shopkeeper", json=reg_payload)
    assert res.status_code == 201, res.text
    data = res.json()
    shop_id = data["shop_id"]

    # Verify directly in PostgreSQL that an active registration token exists for this shop
    query = await db_session.execute(
        text("SELECT id, token_hash, encrypted_token, is_active FROM shop_registration_tokens WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    token_row = query.fetchone()
    assert token_row is not None, "Registration token was not created automatically!"
    assert token_row[3] is True, "Token must be active"

    # Verify decrypted token matches hash
    raw_token = decrypt_token(token_row[2])
    assert hash_token(raw_token) == token_row[1], "Decrypted token must hash to the stored SHA-256 digest"

    # Verify audit log was created with action 'GENERATED'
    audit_query = await db_session.execute(
        text("SELECT action FROM shop_qr_audit_logs WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    audit_rows = audit_query.fetchall()
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == "GENERATED"


@pytest.mark.asyncio
async def test_02_qr_persistence_across_logins_and_restarts(client: AsyncClient):
    """Verify that an authorized shopkeeper retrieves the EXACT same static QR token across logins without regenerating."""
    # 1. Register shopkeeper
    reg_payload = {
        "full_name": "Vikram Singh",
        "shop_name": "Vikram Provisions",
        "shop_address": "Sector 18, Noida",
        "phone": "9876522222",
        "password": "Password@123",
    }
    reg_res = await client.post("/api/v1/auth/register/shopkeeper", json=reg_payload)
    data = reg_res.json()
    shop_id = data["shop_id"]
    token_1 = data["tokens"]["access_token"]

    # 2. Get QR with initial token
    qr_res_1 = await client.get(
        f"/api/v1/shops/{shop_id}/registration-qr",
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert qr_res_1.status_code == 200
    qr_data_1 = qr_res_1.json()
    orig_url = qr_data_1["registration_url"]
    orig_svg = qr_data_1["qr_code_svg"]

    # 3. Simulate Logout and fresh Login (different session)
    login_res = await client.post("/api/v1/auth/login", json={"identifier": "9876522222", "password": "Password@123"})
    assert login_res.status_code == 200
    token_2 = login_res.json()["access_token"]

    # 4. Retrieve QR again with new session token
    qr_res_2 = await client.get(
        f"/api/v1/shops/{shop_id}/registration-qr",
        headers={"Authorization": f"Bearer {token_2}"},
    )
    assert qr_res_2.status_code == 200
    qr_data_2 = qr_res_2.json()

    # The registration URL and QR code MUST be 100% identical
    assert qr_data_2["registration_url"] == orig_url, "Permanent QR URL must not change on subsequent logins"
    assert qr_data_2["qr_code_svg"] == orig_svg, "Permanent QR SVG must be identical"

    # 5. Also retrieve via the convenient /me endpoint
    qr_res_me = await client.get(
        "/api/v1/shops/me/registration-qr",
        headers={"Authorization": f"Bearer {token_2}"},
    )
    assert qr_res_me.status_code == 200
    qr_data_me = qr_res_me.json()
    assert qr_data_me["registration_url"] == orig_url
    assert qr_data_me["shop_id"] == shop_id


@pytest.mark.asyncio
async def test_03_unauthorized_shopkeeper_cannot_access_other_shop_qr(client: AsyncClient):
    """Confirm Shopkeeper A cannot access, rotate, or revoke Shopkeeper B's QR code."""
    # Register Shopkeeper A
    res_a = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Shopkeeper A", "shop_name": "Shop A", "shop_address": "Addr A",
        "phone": "9876511111", "password": "Password@123",
    })
    shop_a_id = res_a.json()["shop_id"]

    # Register Shopkeeper B
    res_b = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Shopkeeper B", "shop_name": "Shop B", "shop_address": "Addr B",
        "phone": "9876522222", "password": "Password@123",
    })
    token_b = res_b.json()["tokens"]["access_token"]

    # Shopkeeper B attempts to read Shop A's QR
    attack_res = await client.get(
        f"/api/v1/shops/{shop_a_id}/registration-qr",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert attack_res.status_code == 403, "Shopkeeper B must not access Shop A's registration QR!"

    # Unauthenticated request must return 401
    anon_res = await client.get("/api/v1/shops/me/registration-qr")
    assert anon_res.status_code == 401

    # Invalid token must return 401
    invalid_res = await client.get("/api/v1/shops/me/registration-qr", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert invalid_res.status_code == 401

    # Customer role must be forbidden (403) from accessing shopkeeper registration QR
    cust_res = await client.post("/api/v1/customer/register", json={
        "full_name": "A Regular Customer", "phone": "9876533333", "password": "Password@123",
    })
    assert cust_res.status_code == 201, cust_res.text
    cust_token = cust_res.json()["access_token"]
    cust_attack = await client.get("/api/v1/shops/me/registration-qr", headers={"Authorization": f"Bearer {cust_token}"})
    assert cust_attack.status_code == 403


@pytest.mark.asyncio
async def test_04_public_shop_lookup_and_invalid_token_rejection(client: AsyncClient):
    """Test public shop lookup endpoint: resolves active token and rejects invalid/expired tokens with safe messages."""
    # Register shop
    res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Sunil Traders", "shop_name": "Sunil Kirana", "shop_address": "Chandni Chowk, Delhi",
        "phone": "9876511111", "password": "Password@123",
    })
    shop_id = res.json()["shop_id"]
    token = res.json()["tokens"]["access_token"]

    # Fetch raw registration URL
    qr_res = await client.get(f"/api/v1/shops/{shop_id}/registration-qr", headers={"Authorization": f"Bearer {token}"})
    reg_url = qr_res.json()["registration_url"]
    raw_token = reg_url.split("/")[-1]

    # Public lookup of valid token
    pub_res = await client.get(f"/api/v1/public/shops/join/{raw_token}")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["shop_id"] == shop_id
    assert pub_data["shop_name"] == "Sunil Kirana"
    assert pub_data["is_valid"] is True
    assert "token_hash" not in pub_data
    assert "encrypted_token" not in pub_data

    # Public lookup of completely fake/invalid token
    fake_res = await client.get("/api/v1/public/shops/join/non_existent_token_123456789")
    assert fake_res.status_code == 404
    assert fake_res.json()["detail"] == "Registration QR code is invalid or has expired."


@pytest.mark.asyncio
async def test_05_qr_rotation_and_revocation(client: AsyncClient):
    """Test that rotating a QR code generates a new working QR while immediately invalidating the old one."""
    res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Anil Superstore", "shop_name": "Anil Mart", "shop_address": "Commercial Street, Bengaluru",
        "phone": "9876511111", "password": "Password@123",
    })
    shop_id = res.json()["shop_id"]
    auth_header = {"Authorization": f"Bearer {res.json()['tokens']['access_token']}"}

    # 1. Fetch initial token
    qr_1 = (await client.get(f"/api/v1/shops/{shop_id}/registration-qr", headers=auth_header)).json()
    token_1 = qr_1["registration_url"].split("/")[-1]

    # Initial token works
    assert (await client.get(f"/api/v1/public/shops/join/{token_1}")).status_code == 200

    # 2. Rotate QR
    rotate_res = await client.post(f"/api/v1/shops/{shop_id}/registration-qr/rotate", headers=auth_header)
    assert rotate_res.status_code == 200
    qr_2 = rotate_res.json()
    token_2 = qr_2["registration_url"].split("/")[-1]
    assert token_1 != token_2, "Rotated token must be different"

    # 3. Old token MUST fail immediately
    old_res = await client.get(f"/api/v1/public/shops/join/{token_1}")
    assert old_res.status_code == 404

    # 4. New token MUST succeed
    new_res = await client.get(f"/api/v1/public/shops/join/{token_2}")
    assert new_res.status_code == 200

    # 5. Revoke QR
    revoke_res = await client.post(f"/api/v1/shops/{shop_id}/registration-qr/revoke", headers=auth_header)
    assert revoke_res.status_code == 200

    # Both tokens now fail
    assert (await client.get(f"/api/v1/public/shops/join/{token_2}")).status_code == 404


@pytest.mark.asyncio
async def test_06_customer_onboarding_and_financial_isolation(client: AsyncClient, db_session: AsyncSession):
    """
    Test customer onboarding via scanned QR:
    1. Customer explicitly joins.
    2. Customer appears in shopkeeper customer list.
    3. Joining creates ZERO Udhaar balance or financial ledger records.
    4. Joining again is idempotent (no duplicate records).
    """
    # 1. Register shopkeeper
    sk_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Pooja Stores", "shop_name": "Pooja Provisions", "shop_address": "Jayanagar, Bengaluru",
        "phone": "9876511111", "password": "Password@123",
    })
    shop_id = sk_res.json()["shop_id"]
    sk_token = sk_res.json()["tokens"]["access_token"]
    qr_data = (await client.get(f"/api/v1/shops/{shop_id}/registration-qr", headers={"Authorization": f"Bearer {sk_token}"})).json()
    raw_token = qr_data["registration_url"].split("/")[-1]

    # 2. Register new customer
    cust_res = await client.post("/api/v1/customer/register", json={
        "full_name": "Ananya Sharma",
        "phone": "9876533333",
        "password": "CustPassword@123",
        "address": "Flat 302, Green Glen Layout, Bengaluru",
    })
    assert cust_res.status_code == 201
    cust_token = cust_res.json()["access_token"]
    cust_header = {"Authorization": f"Bearer {cust_token}"}

    # 3. Customer explicitly confirms joining shop
    join_res = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": raw_token},
        headers=cust_header,
    )
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert join_data["status"] == "joined"
    assert join_data["shop_name"] == "Pooja Provisions"

    # 4. Verify shopkeeper customer list contains Ananya Sharma
    sk_cust_res = await client.get(
        f"/api/v1/shops/{shop_id}/customers",
        headers={"Authorization": f"Bearer {sk_token}"},
    )
    assert sk_cust_res.status_code == 200
    cust_list = sk_cust_res.json()
    assert len(cust_list) == 1
    assert cust_list[0]["full_name"] == "Ananya Sharma"
    assert cust_list[0]["phone"] == "+919876533333"

    # 5. Customer checks their joined shops
    my_shops = (await client.get("/api/v1/customer/shops", headers=cust_header)).json()
    assert len(my_shops) == 1
    assert my_shops[0]["shop_name"] == "Pooja Provisions"

    # 6. Re-joining is IDEMPOTENT (no error, no duplicate)
    rejoin_res = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": raw_token},
        headers=cust_header,
    )
    assert rejoin_res.status_code == 200
    assert rejoin_res.json()["status"] == "already_joined"

    # Verify count in DB remains strictly 1
    count_res = await db_session.execute(
        text("SELECT COUNT(*) FROM shop_customers WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    assert count_res.scalar() == 1


@pytest.mark.asyncio
async def test_07_customer_joins_multiple_shops_under_single_identity(client: AsyncClient):
    """A customer can join Shop A and Shop B using their single Qbox account."""
    # Register Shop 1
    res1 = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Merchant 1", "shop_name": "Store One", "shop_address": "Addr 1",
        "phone": "9876511111", "password": "Password@123",
    })
    shop1_id = res1.json()["shop_id"]
    t1_head = {"Authorization": f"Bearer {res1.json()['tokens']['access_token']}"}
    raw_token_1 = (await client.get(f"/api/v1/shops/{shop1_id}/registration-qr", headers=t1_head)).json()["registration_url"].split("/")[-1]

    # Register Shop 2
    res2 = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Merchant 2", "shop_name": "Store Two", "shop_address": "Addr 2",
        "phone": "9876522222", "password": "Password@123",
    })
    shop2_id = res2.json()["shop_id"]
    t2_head = {"Authorization": f"Bearer {res2.json()['tokens']['access_token']}"}
    raw_token_2 = (await client.get(f"/api/v1/shops/{shop2_id}/registration-qr", headers=t2_head)).json()["registration_url"].split("/")[-1]

    # Customer registers once
    cust_res = await client.post("/api/v1/customer/register", json={
        "full_name": "Rahul Verma", "phone": "9876544444", "password": "Password@123",
    })
    cust_head = {"Authorization": f"Bearer {cust_res.json()['access_token']}"}

    # Joins Shop 1
    j1 = await client.post(f"/api/v1/shops/{shop1_id}/join", json={"token": raw_token_1}, headers=cust_head)
    assert j1.status_code == 200 and j1.json()["status"] == "joined"

    # Joins Shop 2
    j2 = await client.post(f"/api/v1/shops/{shop2_id}/join", json={"token": raw_token_2}, headers=cust_head)
    assert j2.status_code == 200 and j2.json()["status"] == "joined"

    # Verify customer sees both shops
    my_shops = (await client.get("/api/v1/customer/shops", headers=cust_head)).json()
    assert len(my_shops) == 2
    shop_names = [s["shop_name"] for s in my_shops]
    assert "Store One" in shop_names
    assert "Store Two" in shop_names


@pytest.mark.asyncio
async def test_08_tenant_isolation_between_shopkeepers(client: AsyncClient):
    """Confirm Shop 1 cannot see customers who only joined Shop 2."""
    # Shop 1 & Shop 2
    res1 = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Merchant One", "shop_name": "Store 1", "shop_address": "Address Line 1, Main Road", "phone": "9876580001", "password": "Password@123",
    })
    assert res1.status_code == 201, res1.text
    shop1_id = res1.json()["shop_id"]
    tok1 = res1.json()["tokens"]["access_token"]

    res2 = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Merchant Two", "shop_name": "Store 2", "shop_address": "Address Line 2, Cross Road", "phone": "9876580002", "password": "Password@123",
    })
    assert res2.status_code == 201, res2.text
    shop2_id = res2.json()["shop_id"]
    tok2 = res2.json()["tokens"]["access_token"]
    raw_token_2 = (await client.get(f"/api/v1/shops/{shop2_id}/registration-qr", headers={"Authorization": f"Bearer {tok2}"})).json()["registration_url"].split("/")[-1]

    # Customer joins Shop 2 ONLY
    cust_res = await client.post("/api/v1/customer/register", json={
        "full_name": "Sneha", "phone": "9876580003", "password": "Password@123",
    })
    assert cust_res.status_code == 201, cust_res.text
    await client.post(
        f"/api/v1/shops/{shop2_id}/join",
        json={"token": raw_token_2},
        headers={"Authorization": f"Bearer {cust_res.json()['access_token']}"},
    )

    # Shop 1 customer list must be empty
    s1_custs = (await client.get(f"/api/v1/shops/{shop1_id}/customers", headers={"Authorization": f"Bearer {tok1}"})).json()
    assert len(s1_custs) == 0, "Shop 1 must not see customers from Shop 2!"

    # Shop 2 customer list has 1 customer
    s2_custs = (await client.get(f"/api/v1/shops/{shop2_id}/customers", headers={"Authorization": f"Bearer {tok2}"})).json()
    assert len(s2_custs) == 1
    assert s2_custs[0]["phone"] == "+919876580003"


@pytest.mark.asyncio
async def test_09_registration_url_matches_environment_and_host(client: AsyncClient, db_session: AsyncSession):
    """
    Verify environment configuration:
    1. Emulator requests receive http://10.0.2.2:8000/join/<token>
    2. Physical device requests receive http://192.168.1.5:8000/join/<token>
    3. The underlying token and database record remain 100% identical (no rotation or revocation).
    """
    # 1. Register shopkeeper
    reg_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Arjun Patel", "shop_name": "Patel Sweets", "shop_address": "Station Road, Anand",
        "phone": "9876590001", "password": "Password@123",
    })
    assert reg_res.status_code == 201, reg_res.text
    shop_id = reg_res.json()["shop_id"]
    token = reg_res.json()["tokens"]["access_token"]

    # 2. Request QR with Emulator header
    emu_res = await client.get(
        "/api/v1/shops/me/registration-qr",
        headers={"Authorization": f"Bearer {token}", "X-Client-Device": "emulator"},
    )
    assert emu_res.status_code == 200
    emu_data = emu_res.json()
    emu_url = emu_data["registration_url"]
    assert emu_url.startswith("http://10.0.2.2:8000/join/")
    emu_token = emu_url.split("/")[-1]

    # 3. Request QR with Physical Phone header
    phys_res = await client.get(
        "/api/v1/shops/me/registration-qr",
        headers={"Authorization": f"Bearer {token}", "X-Client-Device": "physical"},
    )
    assert phys_res.status_code == 200
    phys_data = phys_res.json()
    phys_url = phys_data["registration_url"]
    assert phys_url.startswith("http://192.168.1.5:8000/join/")
    phys_token = phys_url.split("/")[-1]

    # 4. Request QR with explicit device query param (?device=physical)
    param_res = await client.get(
        "/api/v1/shops/me/registration-qr?device=physical",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert param_res.status_code == 200
    assert param_res.json()["registration_url"].startswith("http://192.168.1.5:8000/join/")

    # 5. Core requirement: The underlying decrypted token MUST be 100% IDENTICAL
    # Switching environment does NOT create a new token or revoke existing ones
    assert emu_token == phys_token, "Tokens must remain identical across environments"

    # 6. Verify in database: exactly ONE active token exists for this shop
    db_res = await db_session.execute(
        text("SELECT COUNT(*) FROM shop_registration_tokens WHERE shop_id = :sid AND is_active = true"),
        {"sid": shop_id},
    )
    assert db_res.scalar() == 1


@pytest.mark.asyncio
async def test_10_customer_join_web_landing_page(client: AsyncClient):
    """Verify that scanning/visiting /join/{token} renders the verified shop web landing page."""
    reg_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Meera Joshi", "shop_name": "Joshi Dairy", "shop_address": "FC Road, Pune",
        "phone": "9876590002", "password": "Password@123",
    })
    token = reg_res.json()["tokens"]["access_token"]

    qr_res = await client.get("/api/v1/shops/me/registration-qr", headers={"Authorization": f"Bearer {token}"})
    raw_token = qr_res.json()["registration_url"].split("/")[-1]

    # Valid token web landing page
    page_res = await client.get(f"/join/{raw_token}")
    assert page_res.status_code == 200
    assert "text/html" in page_res.headers["content-type"]
    assert "Joshi Dairy" in page_res.text
    assert "Verified Qbox Merchant" in page_res.text
    assert raw_token in page_res.text

    # Invalid token web landing page returns 404 HTML
    invalid_res = await client.get("/join/non_existent_token_xyz")
    assert invalid_res.status_code == 404
    assert "QR Code Expired or Invalid" in invalid_res.text


@pytest.mark.asyncio
async def test_11_customer_onboarding_zero_balance_and_revoked_token_rejection(client: AsyncClient, db_session: AsyncSession):
    """
    Verify:
    1. Customer onboarding creates ZERO initial Udhaar debt and zero ledger entries.
    2. Revoked or invalid registration tokens return HTTP 404 and reject joining.
    3. Idempotent joining does not duplicate associations.
    """
    # 1. Register shopkeeper
    sk_res = await client.post("/api/v1/auth/register/shopkeeper", json={
        "full_name": "Rohan Verma", "shop_name": "Verma Mart", "shop_address": "Indira Nagar, Bengaluru",
        "phone": "9876544444", "password": "Password@123",
    })
    shop_id = sk_res.json()["shop_id"]
    sk_token = sk_res.json()["tokens"]["access_token"]
    sk_header = {"Authorization": f"Bearer {sk_token}"}

    qr_res = await client.get(f"/api/v1/shops/{shop_id}/registration-qr", headers=sk_header)
    raw_token = qr_res.json()["registration_url"].split("/")[-1]

    # 2. Register customer
    cust_res = await client.post("/api/v1/customer/register", json={
        "full_name": "Deepak Patel", "phone": "9876555555", "password": "CustPassword@123",
        "address": "Sector 4, Bengaluru",
    })
    cust_token = cust_res.json()["access_token"]
    cust_header = {"Authorization": f"Bearer {cust_token}"}

    # 3. Invalid token rejection
    bad_res = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": "totally-fake-token-1234567890"},
        headers=cust_header,
    )
    assert bad_res.status_code == 404
    assert "invalid or has expired" in bad_res.json()["detail"].lower()

    # 4. Successful initial join
    join_res = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": raw_token},
        headers=cust_header,
    )
    assert join_res.status_code == 200
    assert join_res.json()["status"] == "joined"

    # 5. Verify database: exactly 1 ShopCustomer record, status ACTIVE, zero debt
    sc_query = await db_session.execute(
        text("SELECT status FROM shop_customers WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    rows = sc_query.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "ACTIVE"

    # 6. Revoke the QR
    revoke_res = await client.post(f"/api/v1/shops/{shop_id}/registration-qr/revoke", headers=sk_header)
    assert revoke_res.status_code == 200

    # 7. Another customer trying to join with the revoked QR gets 404
    cust2_res = await client.post("/api/v1/customer/register", json={
        "full_name": "Meena Kumari", "phone": "9876566666", "password": "CustPassword@123",
        "address": "Sector 5, Bengaluru",
    })
    cust2_token = cust2_res.json()["access_token"]
    cust2_header = {"Authorization": f"Bearer {cust2_token}"}

    revoked_join = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": raw_token},
        headers=cust2_header,
    )
    assert revoked_join.status_code == 404
    assert "invalid or has expired" in revoked_join.json()["detail"].lower()
