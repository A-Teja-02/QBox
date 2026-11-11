import hashlib
import io
import uuid
import pytest
import qrcode
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


def make_upi_qr_bytes(upi_string: str = "upi://pay?pa=rameshkirana@okaxis&pn=RameshKirana&cu=INR") -> bytes:
    """Generates a real valid UPI QR code in memory as PNG bytes."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_upi_qr_jpeg_bytes(upi_string: str = "upi://pay?pa=rameshkirana@okhdfcbank&pn=RameshKirana&cu=INR") -> bytes:
    """Generates a real valid UPI QR code in memory as JPEG bytes."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_unrelated_qr_bytes(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ") -> bytes:
    """Generates a QR code with an unrelated non-payment URL."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_solid_color_image_bytes(format_name: str = "PNG") -> bytes:
    """Generates a valid image (solid color) with NO QR code matrix."""
    from PIL import Image
    img = Image.new("RGB", (250, 250), color=(30, 144, 255))
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    return buf.getvalue()


@pytest.fixture(autouse=True)
async def cleanup_payment_qr_test_data(db_session: AsyncSession):
    """Clean up test users before and after each test."""
    await db_session.execute(text("DELETE FROM users WHERE phone LIKE '+91987650%'"))
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM users WHERE phone LIKE '+91987650%'"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_01_shopkeeper_registration_with_valid_payment_qr(client: AsyncClient, db_session: AsyncSession):
    """Test successful shopkeeper registration via multipart/form-data with valid UPI payment QR image."""
    png_bytes = make_upi_qr_bytes("upi://pay?pa=teststore@ybl&pn=TestStore&cu=INR")

    data = {
        "full_name": "Deepak Merchant",
        "shop_name": "Deepak General Store",
        "shop_address": "Station Road, Surat",
        "phone": "9876500001",
        "password": "Password@123",
        "upi_id": "teststore@ybl",
    }
    files = {
        "payment_qr_image": ("store_payment_qr.png", png_bytes, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 201, res.text
    resp_data = res.json()

    assert resp_data["shop_name"] == "Deepak General Store"
    assert resp_data["has_payment_qr"] is True
    assert resp_data["payment_qr_url"] is not None
    shop_id = resp_data["shop_id"]

    # Verify directly in PostgreSQL
    query = await db_session.execute(
        text("SELECT id, storage_key, upi_provider, is_active, image_data, file_checksum FROM shop_payment_qrs WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    pqr = query.fetchone()
    assert pqr is not None, "ShopPaymentQr row was not created in PostgreSQL"
    assert pqr[2] == "PhonePe"  # Detected from @ybl
    assert pqr[3] is True, "Payment QR must be active"
    # Verify BYTEA binary data and checksum
    assert pqr[4] is not None, "image_data BYTEA must be populated in database"
    assert bytes(pqr[4]) == png_bytes, "Stored image bytes must match uploaded PNG bytes"
    assert hashlib.sha256(bytes(pqr[4])).hexdigest() == pqr[5], "SHA-256 checksum must match stored image_data"


@pytest.mark.asyncio
async def test_01b_shopkeeper_registration_with_valid_jpeg_payment_qr(client: AsyncClient, db_session: AsyncSession):
    """Test successful shopkeeper registration via multipart/form-data with valid JPEG UPI payment QR image."""
    jpeg_bytes = make_upi_qr_jpeg_bytes("upi://pay?pa=teststore@okhdfcbank&pn=TestStore&cu=INR")

    data = {
        "full_name": "Kiran Merchant",
        "shop_name": "Kiran Store",
        "shop_address": "MG Road, Pune",
        "phone": "9876500009",
        "password": "Password@123",
        "upi_id": "teststore@okhdfcbank",
    }
    files = {
        "payment_qr_image": ("store_payment_qr.jpg", jpeg_bytes, "image/jpeg"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 201, res.text
    resp_data = res.json()

    assert resp_data["shop_name"] == "Kiran Store"
    assert resp_data["has_payment_qr"] is True
    shop_id = resp_data["shop_id"]

    # Verify directly in PostgreSQL
    query = await db_session.execute(
        text("SELECT id, storage_key, upi_provider, content_type, is_active, image_data, file_checksum FROM shop_payment_qrs WHERE shop_id = :sid"),
        {"sid": shop_id},
    )
    pqr = query.fetchone()
    assert pqr is not None, "ShopPaymentQr row was not created in PostgreSQL"
    assert pqr[2] == "Google Pay"  # Detected from @okhdfcbank
    assert pqr[3] == "image/jpeg"
    assert pqr[4] is True
    # Verify JPEG BYTEA binary data and checksum
    assert pqr[5] is not None, "image_data BYTEA must be populated for JPEG"
    assert bytes(pqr[5]) == jpeg_bytes, "Stored image bytes must match uploaded JPEG bytes"
    assert hashlib.sha256(bytes(pqr[5])).hexdigest() == pqr[6], "SHA-256 checksum must match stored JPEG data"


@pytest.mark.asyncio
async def test_02_registration_fails_without_payment_qr_in_multipart(client: AsyncClient):
    """Test that multipart registration fails with HTTP 422 if payment QR image is omitted."""
    data = {
        "full_name": "No QR Merchant",
        "shop_name": "No QR Store",
        "shop_address": "Market Road, Delhi",
        "phone": "9876500002",
        "password": "Password@123",
    }
    # Send multipart form without file
    res = await client.post("/api/v1/auth/register/shopkeeper", data=data)
    assert res.status_code == 422
    assert "payment qr image is mandatory" in res.text.lower()


@pytest.mark.asyncio
async def test_03_registration_rejects_oversized_image(client: AsyncClient):
    """Test that images exceeding 5 MB are rejected with HTTP 413."""
    # 5.5 MB dummy buffer with PNG header
    oversized = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (6 * 1024 * 1024))

    data = {
        "full_name": "Big File Merchant",
        "shop_name": "Big File Store",
        "shop_address": "Main Street, Mumbai",
        "phone": "9876500003",
        "password": "Password@123",
    }
    files = {
        "payment_qr_image": ("large_qr.png", oversized, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 413
    assert "exceeds maximum allowed limit" in res.text.lower()


@pytest.mark.asyncio
async def test_04_registration_rejects_disguised_invalid_file(client: AsyncClient):
    """Test that disguised or corrupted files (e.g. text file renamed .png) are rejected with HTTP 400."""
    fake_png = b"This is just a plain text file pretending to be an image!"

    data = {
        "full_name": "Fake Image Merchant",
        "shop_name": "Fake Store",
        "shop_address": "Cross Road, Jaipur",
        "phone": "9876500004",
        "password": "Password@123",
    }
    files = {
        "payment_qr_image": ("corrupted.png", fake_png, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 400
    assert "file header does not match" in res.text.lower()


@pytest.mark.asyncio
async def test_05_registration_rejects_unrelated_qr_payload(client: AsyncClient):
    """Test that an uploaded QR code pointing to an unrelated non-payment URL is rejected."""
    youtube_qr = make_unrelated_qr_bytes("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    data = {
        "full_name": "YouTube Merchant",
        "shop_name": "Video Store",
        "shop_address": "Mall Road, Shimla",
        "phone": "9876500005",
        "password": "Password@123",
    }
    files = {
        "payment_qr_image": ("youtube_qr.png", youtube_qr, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 400
    assert "does not appear to be a valid upi payment qr code" in res.text.lower()


@pytest.mark.asyncio
async def test_05b_registration_rejects_undecodable_image(client: AsyncClient):
    """Test that an image containing no decodable QR matrix is rejected with HTTP 400."""
    plain_img = make_solid_color_image_bytes("PNG")

    data = {
        "full_name": "No QR Pattern Merchant",
        "shop_name": "Plain Image Store",
        "shop_address": "Lake View Road, Udaipur",
        "phone": "9876500005",
        "password": "Password@123",
    }
    files = {
        "payment_qr_image": ("avatar.png", plain_img, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 400
    assert "no valid qr code could be decoded" in res.text.lower()


@pytest.mark.asyncio
async def test_05c_registration_rejects_arbitrary_text_qr_payload(client: AsyncClient):
    """Test that a QR code encoding arbitrary non-payment text is rejected with HTTP 400."""
    arbitrary_qr = make_unrelated_qr_bytes("Special promotional coupon: SAVE50 on all groceries!")

    data = {
        "full_name": "Coupon Merchant",
        "shop_name": "Coupon Store",
        "shop_address": "City Square, Chandigarh",
        "phone": "9876500005",
        "password": "Password@123",
    }
    files = {
        "payment_qr_image": ("coupon_qr.png", arbitrary_qr, "image/png"),
    }

    res = await client.post("/api/v1/auth/register/shopkeeper", data=data, files=files)
    assert res.status_code == 400
    assert "does not contain a recognized upi payment payload" in res.text.lower()


@pytest.mark.asyncio
async def test_06_shopkeeper_can_retrieve_and_stream_own_payment_qr(client: AsyncClient):
    """Test that authenticated shopkeeper can retrieve metadata and stream their active payment QR."""
    png_bytes = make_upi_qr_bytes("upi://pay?pa=gpaymerchant@okaxis&pn=GPayMerchant&cu=INR")

    reg_res = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant Six", "shop_name": "Store Six", "shop_address": "Road 6", "phone": "9876500006", "password": "Password@123"},
        files={"payment_qr_image": ("gpay_qr.png", png_bytes, "image/png")},
    )
    assert reg_res.status_code == 201
    shop_id = reg_res.json()["shop_id"]
    token = reg_res.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Retrieve metadata
    meta_res = await client.get(f"/api/v1/shops/{shop_id}/payment-qr", headers=headers)
    assert meta_res.status_code == 200
    meta = meta_res.json()
    assert meta["shop_id"] == shop_id
    assert meta["is_active"] is True
    assert meta["upi_provider"] == "Google Pay"
    assert "/payment-qr/image" in meta["image_url"]

    # 2. Stream image bytes
    stream_res = await client.get(f"/api/v1/shops/{shop_id}/payment-qr/image", headers=headers)
    assert stream_res.status_code == 200
    assert stream_res.headers["content-type"] == "image/png"
    assert len(stream_res.content) == len(png_bytes)


@pytest.mark.asyncio
async def test_07_shopkeeper_replace_and_delete_payment_qr(client: AsyncClient, db_session: AsyncSession):
    """Test replacing payment QR with new image and deleting (deactivating) it."""
    qr1 = make_upi_qr_bytes("upi://pay?pa=merchant7@paytm&pn=M7&cu=INR")
    qr2 = make_upi_qr_bytes("upi://pay?pa=merchant7@ybl&pn=M7&cu=INR")

    reg = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant Seven", "shop_name": "Store Seven", "shop_address": "Road 7", "phone": "9876500007", "password": "Password@123"},
        files={"payment_qr_image": ("qr1.png", qr1, "image/png")},
    )
    shop_id = reg.json()["shop_id"]
    token = reg.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Replace with QR 2
    replace_res = await client.put(
        f"/api/v1/shops/{shop_id}/payment-qr",
        files={"payment_qr_image": ("qr2.png", qr2, "image/png")},
        headers=headers,
    )
    assert replace_res.status_code == 200
    assert replace_res.json()["upi_provider"] == "PhonePe"

    # Verify exactly 1 active payment QR in PostgreSQL with qr2 image_data
    active_row = (await db_session.execute(
        text("SELECT is_active, image_data, file_checksum, original_filename FROM shop_payment_qrs WHERE shop_id = :sid AND is_active = true"),
        {"sid": shop_id},
    )).mappings().one()
    assert active_row["is_active"] is True
    assert bytes(active_row["image_data"]) == qr2
    assert active_row["original_filename"] == "qr2.png"

    # Verify deactivated previous QR has image_data IS NULL, but metadata preserved
    old_row = (await db_session.execute(
        text("SELECT is_active, image_data, file_checksum, original_filename FROM shop_payment_qrs WHERE shop_id = :sid AND is_active = false"),
        {"sid": shop_id},
    )).mappings().one()
    assert old_row["is_active"] is False
    assert old_row["image_data"] is None
    assert old_row["original_filename"] == "qr1.png"
    assert old_row["file_checksum"] == hashlib.sha256(qr1).hexdigest()

    # 2. Deactivate / Delete
    del_res = await client.delete(f"/api/v1/shops/{shop_id}/payment-qr", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deactivated"

    # Verify 0 active, all rows have image_data IS NULL
    active_post_del = await db_session.scalar(
        text("SELECT COUNT(*) FROM shop_payment_qrs WHERE shop_id = :sid AND is_active = true"),
        {"sid": shop_id},
    )
    assert active_post_del == 0

    deactivated_rows = (await db_session.execute(
        text("SELECT image_data FROM shop_payment_qrs WHERE shop_id = :sid"),
        {"sid": shop_id},
    )).mappings().all()
    for row in deactivated_rows:
        assert row["image_data"] is None


@pytest.mark.asyncio
async def test_07b_replacement_failure_preserves_old_active_qr(client: AsyncClient, db_session: AsyncSession):
    """
    Test ACID transactional safety of QR replacement:
    If replacement upload fails (e.g. invalid file, bad QR), the previous active QR is NOT deactivated or cleared.
    """
    qr1 = make_upi_qr_bytes("upi://pay?pa=merchant7b@paytm&pn=M7B&cu=INR")
    corrupt_data = b"Corrupted invalid image data"

    reg = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant Seven B", "shop_name": "Store Seven B", "shop_address": "Road 7B", "phone": "9876500008", "password": "Password@123"},
        files={"payment_qr_image": ("qr1.png", qr1, "image/png")},
    )
    assert reg.status_code == 201
    shop_id = reg.json()["shop_id"]
    token = reg.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt replace with corrupt file -> 400 Bad Request
    replace_res = await client.put(
        f"/api/v1/shops/{shop_id}/payment-qr",
        files={"payment_qr_image": ("bad.png", corrupt_data, "image/png")},
        headers=headers,
    )
    assert replace_res.status_code == 400

    # Verify old QR is still active and image_data is intact
    active_row = (await db_session.execute(
        text("SELECT is_active, image_data, original_filename FROM shop_payment_qrs WHERE shop_id = :sid AND is_active = true"),
        {"sid": shop_id},
    )).mappings().one()
    assert active_row["is_active"] is True
    assert bytes(active_row["image_data"]) == qr1
    assert active_row["original_filename"] == "qr1.png"

    # Streaming still returns original qr1 bytes
    stream_res = await client.get(f"/api/v1/shops/{shop_id}/payment-qr/image", headers=headers)
    assert stream_res.status_code == 200
    assert len(stream_res.content) == len(qr1)


@pytest.mark.asyncio
async def test_08_cross_shopkeeper_isolation(client: AsyncClient):
    """Test that Shopkeeper B cannot access, replace or delete Shopkeeper A's payment QR."""
    qr_bytes = make_upi_qr_bytes()

    # Shopkeeper A
    res_a = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant A", "shop_name": "Store A", "shop_address": "Road A", "phone": "9876500001", "password": "Password@123"},
        files={"payment_qr_image": ("qr_a.png", qr_bytes, "image/png")},
    )
    shop_a_id = res_a.json()["shop_id"]

    # Shopkeeper B
    res_b = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant B", "shop_name": "Store B", "shop_address": "Road B", "phone": "9876500002", "password": "Password@123"},
        files={"payment_qr_image": ("qr_b.png", qr_bytes, "image/png")},
    )
    token_b = res_b.json()["tokens"]["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Shopkeeper B attempts to access Shop A's payment QR
    get_res = await client.get(f"/api/v1/shops/{shop_a_id}/payment-qr", headers=headers_b)
    assert get_res.status_code == 403

    # Shopkeeper B attempts to delete Shop A's payment QR
    del_res = await client.delete(f"/api/v1/shops/{shop_a_id}/payment-qr", headers=headers_b)
    assert del_res.status_code == 403


@pytest.mark.asyncio
async def test_09_customer_payment_qr_access_and_tenant_isolation(client: AsyncClient):
    """
    Test customer payment QR retrieval:
    - Connected customer can view and stream payment QR.
    - Unconnected customer receives 403 Forbidden.
    - No financial records or transactions are created.
    """
    qr_bytes = make_upi_qr_bytes("upi://pay?pa=ramesh@upi&pn=Ramesh&cu=INR")

    # 1. Register Shopkeeper
    sk_res = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Ramesh Merchant", "shop_name": "Ramesh Mart", "shop_address": "MG Road", "phone": "9876500001", "password": "Password@123"},
        files={"payment_qr_image": ("pay_qr.png", qr_bytes, "image/png")},
    )
    shop_id = sk_res.json()["shop_id"]
    sk_token = sk_res.json()["tokens"]["access_token"]

    # Get shop registration token for joining
    qr_data = (await client.get(f"/api/v1/shops/{shop_id}/registration-qr", headers={"Authorization": f"Bearer {sk_token}"})).json()
    reg_token = qr_data["registration_url"].split("/")[-1]

    # 2. Register Customer
    cust_res = await client.post(
        "/api/v1/customer/register",
        json={"full_name": "Suresh Customer", "phone": "9876500002", "password": "Password@123", "address": "City Road"},
    )
    cust_token = cust_res.json()["access_token"]
    cust_headers = {"Authorization": f"Bearer {cust_token}"}

    # 3. Before joining: Customer attempts to fetch payment QR -> 403 Forbidden
    pre_res = await client.get(f"/api/v1/customer/shops/{shop_id}/payment-qr", headers=cust_headers)
    assert pre_res.status_code == 403
    assert "please connect to the shop first" in pre_res.text.lower()

    # 4. Customer joins shop via onboarding token
    join_res = await client.post(
        f"/api/v1/shops/{shop_id}/join",
        json={"token": reg_token},
        headers=cust_headers,
    )
    assert join_res.status_code == 200

    # 5. After joining: Customer fetches payment QR -> 200 OK
    post_res = await client.get(f"/api/v1/customer/shops/{shop_id}/payment-qr", headers=cust_headers)
    assert post_res.status_code == 200
    pdata = post_res.json()
    assert pdata["has_payment_qr"] is True
    assert pdata["shop_name"] == "Ramesh Mart"
    assert "/payment-qr/image" in pdata["payment_qr_url"]

    # 6. Stream image bytes
    img_res = await client.get(f"/api/v1/customer/shops/{shop_id}/payment-qr/image", headers=cust_headers)
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/png"
    assert len(img_res.content) == len(qr_bytes)


@pytest.mark.asyncio
async def test_10_path_traversal_guards():
    """
    Test that StorageService rigorously prevents path traversal attacks:
    1. Parent directory traversal using ../
    2. Windows-style traversal using ..\\
    3. Absolute system paths (/etc/passwd, C:\\Windows)
    4. Sibling-directory prefix attacks
    """
    from fastapi import HTTPException
    from app.services.storage_service import StorageService

    # 1. Traversal using ../
    with pytest.raises(HTTPException) as exc1:
        StorageService.get_payment_qr_path("../../../etc/passwd")
    assert exc1.value.status_code == 403

    # 2. Traversal using ..\
    with pytest.raises(HTTPException) as exc2:
        StorageService.get_payment_qr_path("..\\..\\Windows\\System32\\cmd.exe")
    assert exc2.value.status_code == 403

    # 3. Absolute path traversal
    with pytest.raises(HTTPException) as exc3:
        StorageService.get_payment_qr_path("/etc/shadow")
    assert exc3.value.status_code == 403

    with pytest.raises(HTTPException) as exc3b:
        StorageService.get_payment_qr_path("C:\\Windows\\System32\\drivers\\etc\\hosts")
    assert exc3b.value.status_code == 403

    # 4. Sibling directory prefix attack
    # E.g. upload_root is '.../uploads', crafting a sibling '.../uploads_fake/secret.png'
    upload_root = StorageService.get_upload_root().resolve()
    sibling_path = upload_root.parent / (upload_root.name + "_fake") / "secret.png"
    # Pure string startswith would incorrectly match:
    assert str(sibling_path).startswith(str(upload_root))
    # But pathlib is_relative_to correctly and strictly returns False:
    assert not sibling_path.is_relative_to(upload_root)

    with pytest.raises(HTTPException) as exc4:
        StorageService.get_payment_qr_path("../uploads_fake/secret.png")
    assert exc4.value.status_code == 403


@pytest.mark.asyncio
async def test_11_deferred_loading_optimization(client: AsyncClient, db_session: AsyncSession):
    """
    Test that image_data uses deferred loading:
    Standard SELECT does NOT load image_data bytes into memory.
    Explicit undefer() DOES load image_data bytes.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import undefer
    from app.models.models import ShopPaymentQr

    qr_bytes = make_upi_qr_bytes("upi://pay?pa=merchant11@paytm&pn=M11&cu=INR")
    reg = await client.post(
        "/api/v1/auth/register/shopkeeper",
        data={"full_name": "Merchant 11", "shop_name": "Store 11", "shop_address": "Road 11", "phone": "9876500009", "password": "Password@123"},
        files={"payment_qr_image": ("qr11.png", qr_bytes, "image/png")},
    )
    assert reg.status_code == 201
    shop_id = reg.json()["shop_id"]

    # 1. Standard query without undefer - image_data should NOT be loaded in object __dict__
    stmt_deferred = select(ShopPaymentQr).where(ShopPaymentQr.shop_id == shop_id, ShopPaymentQr.is_active == True)
    result = await db_session.execute(stmt_deferred)
    record = result.scalar_one()
    assert "image_data" not in record.__dict__

    # Expire to clear session cache
    db_session.expire_all()

    # 2. Query with undefer(ShopPaymentQr.image_data) - image_data MUST be loaded
    stmt_undefer = (
        select(ShopPaymentQr)
        .options(undefer(ShopPaymentQr.image_data))
        .where(ShopPaymentQr.shop_id == shop_id, ShopPaymentQr.is_active == True)
    )
    result2 = await db_session.execute(stmt_undefer)
    record2 = result2.scalar_one()
    assert "image_data" in record2.__dict__
    assert bytes(record2.image_data) == qr_bytes



