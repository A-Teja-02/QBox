import hashlib
import io
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, status
from PIL import Image

from app.core.config import settings

# Supported MIME types and signatures
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"


class StorageService:
    @classmethod
    def get_upload_root(cls) -> Path:
        root = settings.UPLOAD_DIR.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def validate_and_inspect_image(
        cls,
        file_bytes: bytes,
        original_filename: str,
    ) -> Dict[str, Any]:
        """
        Rigorously validates uploaded image bytes:
        1. Size limit (max 5 MB).
        2. Extension whitelist.
        3. Magic bytes / file signatures.
        4. Pillow structural and dimension validation.
        5. OpenCV QR payload decoding (rejects unrelated QR codes).
        """
        # 1. Size check
        file_size = len(file_bytes)
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )
        if file_size > settings.MAX_PAYMENT_QR_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of 5 MB.",
            )

        # 2. Extension check
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension '{ext}'. Only PNG, JPG, and JPEG images are allowed.",
            )

        # 3. Magic bytes verification
        if ext == ".png":
            if not file_bytes.startswith(MAGIC_PNG):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File header does not match a valid PNG image.",
                )
            content_type = "image/png"
        else:
            if not file_bytes.startswith(MAGIC_JPEG):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File header does not match a valid JPEG image.",
                )
            content_type = "image/jpeg"

        # 4. Pillow inspection
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
                format_name = img.format.upper() if img.format else ""
                if format_name not in ("PNG", "JPEG"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unsupported image format '{format_name}'. Only PNG and JPEG are supported.",
                    )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Corrupted or invalid image file: {str(e)}",
            )

        # Re-open for dimensions check
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.size
                if width < 100 or height < 100:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Image dimensions ({width}x{height}) are too small for a readable QR code. Minimum is 100x100.",
                    )
                if width > 4096 or height > 4096:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Image dimensions ({width}x{height}) exceed maximum allowed dimension of 4096x4096.",
                    )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to read image dimensions: {str(e)}",
            )

        # 5. QR Code detection & payload inspection (must decode a valid UPI QR)
        upi_provider = "UPI Standee / App QR"
        detected_upi_id: Optional[str] = None
        decoded_payload: Optional[str] = None

        try:
            import cv2
            import numpy as np

            nparr = np.frombuffer(file_bytes, np.uint8)
            cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if cv_img is not None:
                detector = cv2.QRCodeDetector()
                val, _, _ = detector.detectAndDecode(cv_img)
                if val and val.strip():
                    decoded_payload = val.strip()
        except Exception:
            pass

        if not decoded_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No valid QR code could be decoded from the uploaded image. "
                    "Please upload a clear, legible payment QR code image from PhonePe, Google Pay, "
                    "Paytm, BHIM, or your bank."
                ),
            )

        payload_lower = decoded_payload.lower()
        if payload_lower.startswith("upi://pay") or "upi://" in payload_lower:
            # Valid UPI payment payload
            try:
                parsed = urlparse(decoded_payload)
                query_params = parse_qs(parsed.query)
                pa = query_params.get("pa", [None])[0]
                if pa:
                    detected_upi_id = pa
                    # Classify provider from handle
                    if "@paytm" in pa.lower():
                        upi_provider = "Paytm"
                    elif any(h in pa.lower() for h in ("@ybl", "@ibl", "@axl")):
                        upi_provider = "PhonePe"
                    elif any(h in pa.lower() for h in ("@okaxis", "@okhdfcbank", "@okicici", "@oksbi")):
                        upi_provider = "Google Pay"
                    elif "@upi" in pa.lower():
                        upi_provider = "BHIM"
                    elif any(bank in pa.lower() for bank in ("@sbi", "@hdfc", "@icici", "@axis")):
                        upi_provider = "Bank UPI QR"
                    else:
                        upi_provider = "UPI QR"
            except Exception:
                upi_provider = "UPI QR"
        elif payload_lower.startswith("http://") or payload_lower.startswith("https://"):
            # Non-UPI URL (e.g., website link, social media, phishing)
            # Check if it's a known UPI payment gateway redirect URL
            if any(k in payload_lower for k in ("paytm.me", "phonepe.com", "gpay.app", "upi")):
                upi_provider = "App Payment QR"
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "The uploaded QR code does not appear to be a valid UPI payment QR code "
                        "(detected non-payment link). Please upload a valid PhonePe, Google Pay, "
                        "Paytm, BHIM, or Bank UPI QR code."
                    ),
                )
        elif not any(k in payload_lower for k in ("upi", "pay", "vpa")):
            # Arbitrary text that has no UPI keywords
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The uploaded QR code does not contain a recognized UPI payment payload. "
                    "Please upload a valid merchant payment QR code from PhonePe, Google Pay, "
                    "Paytm, BHIM, or your bank."
                ),
            )

        checksum = hashlib.sha256(file_bytes).hexdigest()

        return {
            "content_type": content_type,
            "file_size": file_size,
            "checksum": checksum,
            "ext": ext,
            "upi_provider": upi_provider,
            "detected_upi_id": detected_upi_id,
            "decoded_payload": decoded_payload,
        }

    @classmethod
    def save_payment_qr(
        cls,
        shop_id: uuid.UUID,
        file_bytes: bytes,
        original_filename: str,
    ) -> Dict[str, Any]:
        """
        Validates image data and returns metadata, storage_key, and image_data for PostgreSQL BYTEA persistence.
        """
        meta = cls.validate_and_inspect_image(file_bytes, original_filename)

        ext = meta["ext"]
        file_uuid = uuid.uuid4()
        storage_key = f"db://payment_qrs/{shop_id}/{file_uuid}{ext}"

        return {
            "storage_key": storage_key,
            "original_filename": Path(original_filename).name[:255],
            "content_type": meta["content_type"],
            "file_size_bytes": meta["file_size"],
            "file_checksum": meta["checksum"],
            "upi_provider": meta["upi_provider"],
            "detected_upi_id": meta["detected_upi_id"],
            "decoded_payload": meta["decoded_payload"],
            "image_data": file_bytes,
        }

    @classmethod
    def get_payment_qr_path(cls, storage_key: str) -> Tuple[Path, str]:
        """
        Resolves storage key to an absolute Path and content type.
        Ensures strict boundary checks using pathlib containment.
        """
        root = cls.get_upload_root().resolve()

        # Reject storage keys containing raw traversal sequences
        if "../" in storage_key or "..\\" in storage_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Path traversal attempt detected.",
            )

        # Disallow absolute paths (Unix leading slash, Windows drive letter, or UNC paths)
        raw_path = Path(storage_key)
        if raw_path.is_absolute() or raw_path.drive or storage_key.startswith("/") or storage_key.startswith("\\"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Absolute path traversal attempt.",
            )

        target_path = (root / storage_key).resolve()

        # Enforce strict pathlib containment (blocks ../, ..\, and sibling directory attacks)
        try:
            if not target_path.is_relative_to(root):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Invalid storage key outside upload root.",
                )
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Invalid storage key outside upload root.",
            )

        if not target_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment QR image file not found on storage.",
            )

        ext = target_path.suffix.lower()
        content_type = "image/png" if ext == ".png" else "image/jpeg"
        return target_path, content_type

    @classmethod
    def delete_payment_qr(cls, storage_key: str) -> bool:
        """Safely removes payment QR image file from disk."""
        try:
            target_path, _ = cls.get_payment_qr_path(storage_key)
            if target_path.exists():
                target_path.unlink()
                return True
        except Exception:
            pass
        return False
