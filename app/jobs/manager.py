"""In-memory active job tracker and cancellation manager."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.downloader.progress import DownloadProgressTracker
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ActiveJob:
    """Represents an active in-flight download operation."""

    job_id: str
    telegram_id: int
    progress_tracker: DownloadProgressTracker
    task: Optional[asyncio.Task] = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: float = field(default_factory=time.time)


class JobManager:
    """Manages active job tracking, execution task handles, and user-level cancellation."""

    def __init__(self):
        self._active_jobs: Dict[str, ActiveJob] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        job_id: str,
        telegram_id: int,
        progress_tracker: DownloadProgressTracker,
        task: Optional[asyncio.Task] = None,
    ) -> ActiveJob:
        """Register a new active job."""
        async with self._lock:
            active_job = ActiveJob(
                job_id=job_id,
                telegram_id=telegram_id,
                progress_tracker=progress_tracker,
                task=task,
            )
            self._active_jobs[job_id] = active_job
            logger.debug(f"Registered job {job_id} for user {telegram_id}. Active: {len(self._active_jobs)}")
            return active_job

    async def attach_task(self, job_id: str, task: asyncio.Task) -> None:
        """Attach background asyncio task to job."""
        async with self._lock:
            if job_id in self._active_jobs:
                self._active_jobs[job_id].task = task

    async def unregister(self, job_id: str) -> Optional[ActiveJob]:
        """Unregister completed or terminated job."""
        async with self._lock:
            job = self._active_jobs.pop(job_id, None)
            if job:
                logger.debug(f"Unregistered job {job_id}. Remaining: {len(self._active_jobs)}")
            return job

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a single job by triggering progress tracker cancellation and task cancellation."""
        async with self._lock:
            job = self._active_jobs.get(job_id)
            if not job:
                return False

            job.progress_tracker.cancel()
            job.cancel_event.set()
            if job.task and not job.task.done():
                job.task.cancel()
            logger.info(f"Cancellation triggered for job {job_id}")
            return True

    async def cancel_user_jobs(self, telegram_id: int) -> List[str]:
        """Cancel all running jobs belonging to specific user."""
        cancelled_ids: List[str] = []
        async with self._lock:
            targets = [j for j in self._active_jobs.values() if j.telegram_id == telegram_id]

        for job in targets:
            job.progress_tracker.cancel()
            job.cancel_event.set()
            if job.task and not job.task.done():
                job.task.cancel()
            cancelled_ids.append(job.job_id)

        if cancelled_ids:
            logger.info(f"Cancelled {len(cancelled_ids)} jobs for user {telegram_id}: {cancelled_ids}")
        return cancelled_ids

    def get_user_active_count(self, telegram_id: int) -> int:
        """Return number of currently active jobs for user."""
        return sum(1 for j in self._active_jobs.values() if j.telegram_id == telegram_id)

    def is_job_active(self, job_id: str) -> bool:
        """Check if job ID is currently active."""
        return job_id in self._active_jobs

    def get_active_job(self, job_id: str) -> Optional[ActiveJob]:
        """Get active job details."""
        return self._active_jobs.get(job_id)

    def get_total_active_count(self) -> int:
        """Return total number of currently active jobs."""
        return len(self._active_jobs)


# Global JobManager singleton
job_manager = JobManager()
