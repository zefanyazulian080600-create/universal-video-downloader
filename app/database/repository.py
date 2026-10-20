"""Database repository for User and DownloadJob domain operations."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DownloadJob, User, utc_now


class UserRepository:
    """Repository handling User operations."""

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> User:
        """Fetch existing user or create a new user profile."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
            )
            session.add(user)
            await session.flush()
        else:
            # Update username / first_name if changed
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            await session.flush()

        return user

    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        """Fetch user by Telegram ID."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_preferences(
        session: AsyncSession,
        telegram_id: int,
        **kwargs: Any,
    ) -> Optional[User]:
        """Update user preferences (quality, format, compression, etc.)."""
        user = await UserRepository.get_by_telegram_id(session, telegram_id)
        if not user:
            return None

        allowed_fields = {"default_quality", "preferred_format", "include_metadata", "enable_compression"}
        for k, v in kwargs.items():
            if k in allowed_fields:
                setattr(user, k, v)

        await session.flush()
        return user


class JobRepository:
    """Repository handling DownloadJob tracking and metrics."""

    ACTIVE_STATUSES = ("queued", "inspecting", "downloading", "processing", "uploading")

    @staticmethod
    async def create_job(
        session: AsyncSession,
        job_id: str,
        telegram_id: int,
        url_sanitized: str,
        platform: str,
        title: Optional[str] = None,
    ) -> DownloadJob:
        """Create a new tracked download job."""
        job = DownloadJob(
            id=job_id,
            telegram_id=telegram_id,
            url_sanitized=url_sanitized,
            platform=platform,
            title=title,
            status="queued",
            created_at=utc_now(),
        )
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get_job(session: AsyncSession, job_id: str) -> Optional[DownloadJob]:
        """Get job by ID."""
        stmt = select(DownloadJob).where(DownloadJob.id == job_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_status(
        session: AsyncSession,
        job_id: str,
        status: str,
        file_size: Optional[int] = None,
        duration: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> Optional[DownloadJob]:
        """Update job lifecycle state."""
        job = await JobRepository.get_job(session, job_id)
        if not job:
            return None

        job.status = status
        now = utc_now()

        if status in ("downloading", "inspecting") and not job.started_at:
            job.started_at = now
        elif status in ("completed", "failed", "cancelled"):
            job.completed_at = now

        if file_size is not None:
            job.file_size_bytes = file_size
        if duration is not None:
            job.duration = duration
        if error_message is not None:
            job.error_message = error_message

        await session.flush()
        return job

    @staticmethod
    async def count_active_jobs_for_user(session: AsyncSession, telegram_id: int) -> int:
        """Count active running/queued jobs for a specific user."""
        stmt = (
            select(func.count(DownloadJob.id))
            .where(DownloadJob.telegram_id == telegram_id)
            .where(DownloadJob.status.in_(JobRepository.ACTIVE_STATUSES))
        )
        result = await session.execute(stmt)
        return int(result.scalar() or 0)

    @staticmethod
    async def get_active_jobs_for_user(session: AsyncSession, telegram_id: int) -> List[DownloadJob]:
        """Fetch all active running/queued jobs for a specific user."""
        stmt = (
            select(DownloadJob)
            .where(DownloadJob.telegram_id == telegram_id)
            .where(DownloadJob.status.in_(JobRepository.ACTIVE_STATUSES))
            .order_by(DownloadJob.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_history(
        session: AsyncSession,
        telegram_id: int,
        limit: int = 10,
    ) -> List[DownloadJob]:
        """Fetch recent download jobs for user."""
        stmt = (
            select(DownloadJob)
            .where(DownloadJob.telegram_id == telegram_id)
            .order_by(DownloadJob.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_global_stats(session: AsyncSession) -> Dict[str, Any]:
        """Calculate overall operational statistics."""
        total_stmt = select(func.count(DownloadJob.id))
        completed_stmt = select(func.count(DownloadJob.id)).where(DownloadJob.status == "completed")
        failed_stmt = select(func.count(DownloadJob.id)).where(DownloadJob.status == "failed")
        active_stmt = select(func.count(DownloadJob.id)).where(DownloadJob.status.in_(JobRepository.ACTIVE_STATUSES))

        total = (await session.execute(total_stmt)).scalar() or 0
        completed = (await session.execute(completed_stmt)).scalar() or 0
        failed = (await session.execute(failed_stmt)).scalar() or 0
        active = (await session.execute(active_stmt)).scalar() or 0

        return {
            "total_jobs": total,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "active_jobs": active,
        }

    @staticmethod
    async def cleanup_old_jobs(session: AsyncSession, days: int) -> int:
        """Delete finished jobs older than retention window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            delete(DownloadJob)
            .where(DownloadJob.created_at < cutoff)
            .where(DownloadJob.status.in_(("completed", "failed", "cancelled")))
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)

    @staticmethod
    async def reset_interrupted_jobs(session: AsyncSession) -> int:
        """Mark uncompleted active jobs on startup as failed to maintain database consistency."""
        stmt = (
            update(DownloadJob)
            .where(DownloadJob.status.in_(JobRepository.ACTIVE_STATUSES))
            .values(
                status="failed",
                error_message="Proses terhenti karena restart server bot.",
                completed_at=utc_now(),
            )
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)
