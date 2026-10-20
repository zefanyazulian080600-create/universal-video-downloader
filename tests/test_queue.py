"""Tests for job queue, concurrency control, and job cancellation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.downloader.progress import DownloadProgressTracker
from app.jobs.manager import JobManager
from app.utils.errors import JobCancelledError


@pytest.mark.asyncio
class TestQueueAndManager:
    """Test job management and cancellation flows."""

    # 16. Job cancellation terminates active job and only that job
    async def test_job_cancellation_terminates_process(self):
        manager = JobManager()
        tracker1 = DownloadProgressTracker()
        tracker2 = DownloadProgressTracker()

        task1 = asyncio.create_task(asyncio.sleep(10))
        task2 = asyncio.create_task(asyncio.sleep(10))

        # Register jobs for two different users
        await manager.register("job-1", telegram_id=1001, progress_tracker=tracker1, task=task1)
        await manager.register("job-2", telegram_id=1002, progress_tracker=tracker2, task=task2)

        assert manager.get_user_active_count(1001) == 1
        assert manager.get_user_active_count(1002) == 1

        # User 1001 cancels their jobs
        cancelled = await manager.cancel_user_jobs(1001)
        assert cancelled == ["job-1"]

        # Assert tracker 1 is cancelled and task 1 cancelled
        assert tracker1.is_cancelled is True
        await asyncio.sleep(0)
        assert task1.cancelled() or task1.done()

        # Verify User 1002 job is completely unaffected
        assert tracker2.is_cancelled is False
        assert not task2.cancelled()

        # Clean up task2
        task2.cancel()

class TestProgressTracker:
    """Tracker synchronous hook tests."""

    def test_progress_tracker_raises_on_cancellation(self):
        tracker = DownloadProgressTracker()
        # Normal update
        tracker.yt_dlp_hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 1000})
        assert tracker.current_state.percentage == 10.0

        # Cancel tracker
        tracker.cancel()
        with pytest.raises(JobCancelledError):
            tracker.yt_dlp_hook({"status": "downloading", "downloaded_bytes": 200, "total_bytes": 1000})
