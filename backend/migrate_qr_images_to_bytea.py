"""
Migration script: Backfills active payment QR images from filesystem into PostgreSQL BYTEA.
Verifies SHA-256 checksum for every migrated image and preserves original local files.
"""
import asyncio
import hashlib
import os
import sys
from pathlib import Path

# Ensure backend root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, update
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.models.models import ShopPaymentQr


async def migrate_and_verify_qr_images() -> dict:
    upload_root = settings.UPLOAD_DIR.resolve()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    migrated_count = 0
    verified_count = 0
    already_populated = 0
    missing_file_count = 0

    print(f"[*] Starting Payment QR BYTEA Migration...")
    print(f"[*] Upload root: {upload_root}")

    async with session_factory() as db:
        # 1. Fetch all rows
        query = select(ShopPaymentQr).options(undefer(ShopPaymentQr.image_data))
        result = await db.execute(query)
        records = result.scalars().all()
        total_records = len(records)
        print(f"[*] Found {total_records} records in shop_payment_qrs.")

        for r in records:
            if r.image_data is not None:
                # Verify existing bytea checksum
                calc_hash = hashlib.sha256(r.image_data).hexdigest()
                assert calc_hash == r.file_checksum, f"Checksum mismatch on existing record {r.id}"
                already_populated += 1
                verified_count += 1
                continue

            # Need to backfill from disk
            clean_key = r.storage_key
            if clean_key.startswith("db://"):
                clean_key = clean_key[5:]
            local_path = (upload_root / clean_key).resolve()

            if not local_path.is_file():
                print(f"[!] Warning: File {local_path} not found on disk for record {r.id}")
                missing_file_count += 1
                continue

            # Read file bytes and verify checksum before writing
            with open(local_path, "rb") as f:
                raw_bytes = f.read()

            file_hash = hashlib.sha256(raw_bytes).hexdigest()
            if file_hash != r.file_checksum:
                raise ValueError(
                    f"Integrity error: File {local_path} checksum {file_hash} does not match DB checksum {r.file_checksum}!"
                )

            # Update row with BYTEA
            await db.execute(
                update(ShopPaymentQr)
                .where(ShopPaymentQr.id == r.id)
                .values(image_data=raw_bytes)
            )
            await db.commit()
            migrated_count += 1

            # Verification query: re-read from PostgreSQL and verify checksum
            v_res = await db.execute(
                select(ShopPaymentQr.image_data, ShopPaymentQr.file_checksum)
                .where(ShopPaymentQr.id == r.id)
            )
            v_data, v_chk = v_res.fetchone()
            assert v_data is not None, f"Migration failed: image_data is null for {r.id}"
            db_hash = hashlib.sha256(v_data).hexdigest()
            assert db_hash == v_chk, f"Verification failed: db_hash {db_hash} != {v_chk}"
            verified_count += 1
            print(f"[+] Migrated and verified record {r.id} ({len(v_data)} bytes, checksum verified).")

    await engine.dispose()

    summary = {
        "total_records": total_records,
        "migrated_count": migrated_count,
        "already_populated": already_populated,
        "verified_count": verified_count,
        "missing_file_count": missing_file_count,
    }
    print(f"[*] Migration completed successfully: {summary}")
    return summary


if __name__ == "__main__":
    asyncio.run(migrate_and_verify_qr_images())

