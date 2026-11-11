import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from app.core.config import settings

# Initialize Argon2id Password Hasher
# Memory: 65536 KiB, Time: 3 iterations, Parallelism: 4 threads
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# --- RFC 7519 Compliant HS256 JWT Implementation ---

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("ascii"))


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed HS256 access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())

    to_encode.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp()), "type": "access"})

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(to_encode, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed HS256 refresh token with unique jti and family claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
    if "family" not in to_encode:
        to_encode["family"] = str(uuid.uuid4())

    to_encode.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp()), "type": "refresh"})

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(to_encode, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and cryptographically verifies an HS256 JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        now_ts = int(time.time())
        if payload.get("exp") and payload["exp"] < now_ts:
            return None  # Expired

        return payload
    except Exception:
        return None


# --- In-Memory Rate Limiting for Login Attempts ---
_login_attempts: Dict[str, list[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 900  # 15 minutes


def is_rate_limited(identifier: str) -> bool:
    """Checks if an identifier has exceeded the maximum allowed failed attempts."""
    now = time.time()
    attempts = _login_attempts.get(identifier, [])
    # Filter attempts within the window
    valid_attempts = [t for t in attempts if now - t < LOCKOUT_WINDOW_SECONDS]
    _login_attempts[identifier] = valid_attempts
    return len(valid_attempts) >= MAX_LOGIN_ATTEMPTS


def record_failed_attempt(identifier: str) -> None:
    """Records a failed login attempt for rate limiting."""
    now = time.time()
    if identifier not in _login_attempts:
        _login_attempts[identifier] = []
    _login_attempts[identifier].append(now)


def clear_failed_attempts(identifier: str) -> None:
    """Clears failed attempts upon successful login."""
    _login_attempts.pop(identifier, None)


# --- Cryptographic QR Token Security & Authenticated Encryption (AES-256-GCM) ---
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import qrcode
import qrcode.image.svg


def generate_secure_token() -> str:
    """Generates a cryptographically random, unguessable URL-safe token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Computes SHA-256 hex digest of a raw token for high-performance database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def encrypt_token(raw_token: str) -> str:
    """
    Encrypts a raw token using AES-256-GCM.
    Uses the server-managed QR_ENCRYPTION_KEY stored in environment configuration.
    Returns base64-encoded string: nonce (12 bytes) + ciphertext + 16-byte GCM authentication tag.
    """
    key_bytes = base64.b64decode(settings.QR_ENCRYPTION_KEY)
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12)  # 96-bit unique random nonce
    ciphertext = aesgcm.encrypt(nonce, raw_token.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_token(encrypted_payload: str) -> str:
    """
    Decrypts an AES-256-GCM encrypted token.
    Verifies GCM authenticity tag; raises an error if tampered with or if key is invalid.
    """
    key_bytes = base64.b64decode(settings.QR_ENCRYPTION_KEY)
    aesgcm = AESGCM(key_bytes)
    raw_payload = base64.b64decode(encrypted_payload)
    nonce = raw_payload[:12]
    ciphertext = raw_payload[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def generate_qr_svg(url: str) -> str:
    """Generates a scalable SVG QR code string representing the registration URL."""
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(url, image_factory=factory)
    return img.to_string().decode("utf-8")


