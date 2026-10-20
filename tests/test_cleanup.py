"""Tests for temporary directory security and cleanup routines."""

from pathlib import Path

from app.jobs.cleanup import clean_job_directory, is_safe_subdirectory, startup_cleanup


class TestCleanupSafety:
    """Directory traversal and isolation tests."""

    # 21. Temporary file cleanup does not escape configured workspace
    def test_cleanup_cannot_escape_base_directory(self, tmp_path: Path):
        base_dir = tmp_path / "downloads"
        base_dir.mkdir(parents=True, exist_ok=True)

        # Normal job directory inside base_dir
        safe_job_dir = base_dir / "job_123"
        safe_job_dir.mkdir()
        (safe_job_dir / "test.mp4").touch()

        # Dangerous path outside base_dir
        dangerous_dir = tmp_path / "outside_system_folder"
        dangerous_dir.mkdir()
        sensitive_file = dangerous_dir / "secret.txt"
        sensitive_file.touch()

        # Verify safety check
        assert is_safe_subdirectory(safe_job_dir, base_dir) is True
        assert is_safe_subdirectory(dangerous_dir, base_dir) is False
        assert is_safe_subdirectory(base_dir, base_dir) is False  # Must not delete root itself

        # Attempt to clean dangerous path
        result = clean_job_directory(dangerous_dir, base_dir=base_dir)
        assert result is False
        # Sensitive file must still exist
        assert sensitive_file.exists() is True

        # Clean safe path
        clean_result = clean_job_directory(safe_job_dir, base_dir=base_dir)
        assert clean_result is True
        assert safe_job_dir.exists() is False

    def test_startup_cleanup(self, tmp_path: Path):
        base_dir = tmp_path / "downloads"
        base_dir.mkdir(parents=True, exist_ok=True)

        # Create leftover files
        (base_dir / "leftover1.mp4").touch()
        (base_dir / "leftover2.part").touch()
        sub = base_dir / "old_job"
        sub.mkdir()
        (sub / "video.mp4").touch()

        removed = startup_cleanup(base_dir=base_dir)
        assert removed >= 3
        assert list(base_dir.iterdir()) == []
