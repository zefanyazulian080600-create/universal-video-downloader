"""Tests for database operations, user isolation, and startup crash recovery."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DownloadJob, User
from app.database.repository import JobRepository, UserRepository


@pytest.mark.asyncio
class TestDatabase:
    """Database persistence and integrity tests."""

    # 19. Database can be initialized and used (User & Job CRUD)
    async def test_user_and_job_crud(self, test_db_session: AsyncSession):
        # Create user
        user = await UserRepository.get_or_create(
            session=test_db_session,
            telegram_id=12345678,
            username="testuser",
            first_name="Test",
        )
        assert user.telegram_id == 12345678
        assert user.default_quality == "best"

        # Update preferences
        updated = await UserRepository.update_preferences(
            session=test_db_session,
            telegram_id=12345678,
            default_quality="720p",
            preferred_format="mp3",
        )
        assert updated.default_quality == "720p"
        assert updated.preferred_format == "mp3"

        # Create DownloadJob
        job = await JobRepository.create_job(
            session=test_db_session,
            job_id="job-111",
            telegram_id=12345678,
            url_sanitized="https://youtube.com/watch?v=111",
            platform="YouTube",
            title="Sample Video",
        )
        assert job.id == "job-111"
        assert job.status == "queued"

        # Update Job Status
        updated_job = await JobRepository.update_status(
            session=test_db_session,
            job_id="job-111",
            status="completed",
            file_size=10485760,
            duration=120.5,
        )
        assert updated_job.status == "completed"
        assert updated_job.file_size_bytes == 10485760
        assert updated_job.completed_at is not None

    # 17. User isolation - user cannot see another user's download jobs
    async def test_user_history_isolation(self, test_db_session: AsyncSession):
        user1_id = 11111
        user2_id = 22222

        await UserRepository.get_or_create(test_db_session, user1_id, "user1")
        await UserRepository.get_or_create(test_db_session, user2_id, "user2")

        # Create jobs for user 1
        await JobRepository.create_job(
            test_db_session, "job-u1-1", user1_id, "https://example.com/1", "YouTube", "User1 Private Video"
        )
        # Create jobs for user 2
        await JobRepository.create_job(
            test_db_session, "job-u2-1", user2_id, "https://example.com/2", "TikTok", "User2 Private Video"
        )

        # Retrieve history for user 1
        history_u1 = await JobRepository.get_user_history(test_db_session, user1_id)
        assert len(history_u1) == 1
        assert history_u1[0].id == "job-u1-1"
        assert history_u1[0].title == "User1 Private Video"

        # Retrieve history for user 2
        history_u2 = await JobRepository.get_user_history(test_db_session, user2_id)
        assert len(history_u2) == 1
        assert history_u2[0].id == "job-u2-1"
        assert history_u2[0].title == "User2 Private Video"

        # Verify cross-user leakage is impossible
        u1_job_ids = [j.id for j in history_u1]
        assert "job-u2-1" not in u1_job_ids

    # 24. Restart recovery: interrupted jobs from crash are marked as failed
    async def test_restart_recovery_resets_interrupted_jobs(self, test_db_session: AsyncSession):
        user_id = 99999
        await UserRepository.get_or_create(test_db_session, user_id, "crashed_user")

        # Simulate job that was downloading when power cut or app crashed
        await JobRepository.create_job(
            test_db_session, "crashed-job-1", user_id, "https://example.com/crash", "YouTube", "Crashed Video"
        )
        await JobRepository.update_status(test_db_session, "crashed-job-1", "downloading")

        # On startup, reset_interrupted_jobs runs
        reset_count = await JobRepository.reset_interrupted_jobs(test_db_session)
        assert reset_count == 1

        recovered_job = await JobRepository.get_job(test_db_session, "crashed-job-1")
        assert recovered_job.status == "failed"
        assert "restart" in recovered_job.error_message.lower()
