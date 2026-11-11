from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Required Database Credentials (MUST be set in environment or backend/.env)
    DATABASE_URL: str = Field(..., description="Async PostgreSQL URL: postgresql+asyncpg://user:pass@host:port/db")
    DATABASE_SYNC_URL: str = Field(..., description="Sync PostgreSQL URL: postgresql+psycopg2://user:pass@host:port/db")

    # Required Cryptographic Secrets (MUST be set in environment or backend/.env)
    SECRET_KEY: str = Field(..., min_length=16, description="JWT signing secret key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    QR_ENCRYPTION_KEY: str = Field(..., description="Fernet 32-byte url-safe base64 encryption key")

    # Environment & Network configuration
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Centralized development host, ports & device targeting
    DEV_HOST_IP: str = "192.168.1.5"
    DEV_PORT: int = 8000
    EMULATOR_HOST: str = "10.0.2.2"
    DEV_TARGET: str = "emulator"  # 'emulator' | 'physical'

    # Optional explicit base URL override (if None, resolved automatically by DEV_TARGET/ENVIRONMENT)
    REGISTRATION_BASE_URL: Optional[str] = None

    # Storage settings
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MAX_PAYMENT_QR_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

    @field_validator("DATABASE_URL", "DATABASE_SYNC_URL")
    @classmethod
    def validate_database_urls(cls, v: str) -> str:
        trimmed = v.strip() if v else ""
        if not trimmed:
            raise ValueError("Database connection URL is required and cannot be empty.")
        if "change_me" in trimmed:
            raise ValueError("Insecure placeholder database URL detected. Set real credentials in backend/.env.")
        return trimmed

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        trimmed = v.strip() if v else ""
        if not trimmed or len(trimmed) < 16:
            raise ValueError("SECRET_KEY is required and must be at least 16 characters.")
        if trimmed == "change_me_to_a_secure_random_key_in_production":
            raise ValueError("Placeholder SECRET_KEY detected. Provide a secure key in backend/.env.")
        return trimmed

    @field_validator("QR_ENCRYPTION_KEY")
    @classmethod
    def validate_qr_encryption_key(cls, v: str) -> str:
        trimmed = v.strip() if v else ""
        if not trimmed:
            raise ValueError("QR_ENCRYPTION_KEY is required for payment QR encryption.")
        if trimmed == "change_me_to_base64_32_bytes_key_in_production":
            raise ValueError("Placeholder QR_ENCRYPTION_KEY detected. Provide a valid Fernet key in backend/.env.")
        return trimmed

    @property
    def effective_registration_base_url(self) -> str:
        """
        Resolves the fallback registration base URL:
        1. If REGISTRATION_BASE_URL is explicitly set in .env / env-var, use it.
        2. If ENVIRONMENT == 'production', use https://qbox.app/join (no dev IP in production).
        3. If DEV_TARGET == 'physical', use http://{DEV_HOST_IP}:{DEV_PORT}/join.
        4. Default for emulator: http://{EMULATOR_HOST}:{DEV_PORT}/join.
        """
        if self.REGISTRATION_BASE_URL and self.REGISTRATION_BASE_URL.strip():
            return self.REGISTRATION_BASE_URL.rstrip("/")
        if self.ENVIRONMENT == "production":
            return "https://qbox.app/join"
        if self.DEV_TARGET.lower() in ("physical", "phone", "device"):
            return f"http://{self.DEV_HOST_IP}:{self.DEV_PORT}/join"
        return f"http://{self.EMULATOR_HOST}:{self.DEV_PORT}/join"

    model_config = SettingsConfigDict(
        env_file=[str(BASE_DIR / ".env"), ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


try:
    settings = Settings()
except Exception as e:
    raise RuntimeError(
        f"CRITICAL CONFIGURATION ERROR: Failed to load required application settings.\n"
        f"Ensure backend/.env exists and defines DATABASE_URL, DATABASE_SYNC_URL, SECRET_KEY, and QR_ENCRYPTION_KEY.\n"
        f"Details: {e}"
    ) from e
