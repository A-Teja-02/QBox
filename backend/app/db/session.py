from typing import AsyncGenerator, Callable
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

# Async Engine for FastAPI Runtime
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Sync Engine for Migrations and Tools
sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    pool_pre_ping=True,
)


def get_session_factory() -> Callable[[], AsyncSession]:
    """Dependency that returns the asynchronous session maker."""
    return AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an asynchronous database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

