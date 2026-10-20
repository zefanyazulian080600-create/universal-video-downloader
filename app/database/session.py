"""Async database session engine and lifecycle management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Base
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        # Ensure parent directory exists for SQLite database files
        if "sqlite" in settings.database_url:
            db_path = settings.database_url.split("///")[-1]
            if db_path and not db_path.startswith(":memory:"):
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a transactional database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database schemas asynchronously."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schemas initialized successfully.")


async def close_db() -> None:
    """Dispose database engine connections gracefully."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine connections closed.")
