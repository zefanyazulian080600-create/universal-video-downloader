"""SQLAlchemy 2.x async database models.

Includes User preferences and DownloadJob tracking. Schema is designed
to be fully portable between SQLite (with aiosqlite) and PostgreSQL (with asyncpg).
"""

from datetime import datetime, timezone
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class for SQLAlchemy models."""
    pass


class User(Base):
    """Telegram bot user profile and preferences."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=True)
    first_name = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # User Preferences
    default_quality = Column(String(20), default="best", nullable=False)  # best, 1080p, 720p, 480p, 360p, audio
    preferred_format = Column(String(10), default="mp4", nullable=False)  # mp4, mp3
    include_metadata = Column(Boolean, default=True, nullable=False)
    enable_compression = Column(Boolean, default=False, nullable=False)

    # Relationships
    jobs = relationship("DownloadJob", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} quality={self.default_quality}>"


class DownloadJob(Base):
    """Tracks media download lifecycle and audit metrics."""

    __tablename__ = "download_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"), index=True, nullable=False)
    url_sanitized = Column(Text, nullable=False)
    platform = Column(String(50), default="Unknown", nullable=False)
    title = Column(String(255), nullable=True)
    
    # Status: queued, inspecting, downloading, processing, uploading, completed, failed, cancelled
    status = Column(String(20), default="queued", index=True, nullable=False)

    file_size_bytes = Column(BigInteger, nullable=True)
    duration = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="jobs")

    def __repr__(self) -> str:
        return f"<DownloadJob id={self.id} status={self.status} platform={self.platform}>"
