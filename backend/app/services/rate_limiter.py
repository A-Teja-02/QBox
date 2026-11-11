import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import RateLimitEvent


class SharedRateLimiter:
    """
    PostgreSQL-backed shared rate limiter suitable for multi-worker and multi-instance deployments.
    Provides distributed sliding window rate limiting with zero external dependencies.
    """

    @staticmethod
    async def check_rate_limit(
        db: AsyncSession,
        key: str,
        max_requests: int = 30,
        window_seconds: int = 60,
    ) -> bool:
        """
        Returns True if the request is allowed within rate limits; False if exceeded.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)

        # 1. Count events in the active window
        count_query = select(func.count(RateLimitEvent.id)).where(
            RateLimitEvent.key == key,
            RateLimitEvent.created_at >= window_start,
        )
        count_res = await db.execute(count_query)
        current_count = count_res.scalar() or 0

        if current_count >= max_requests:
            return False

        # 2. Record this event
        new_event = RateLimitEvent(
            id=uuid.uuid4(),
            key=key,
            created_at=now,
        )
        db.add(new_event)
        await db.commit()

        # 3. Opportunistic cleanup of stale events older than 1 hour (non-blocking)
        stale_cutoff = now - timedelta(hours=1)
        cleanup_query = delete(RateLimitEvent).where(RateLimitEvent.created_at < stale_cutoff)
        await db.execute(cleanup_query)
        await db.commit()

        return True

