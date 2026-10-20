"""Safe cleanup routines for temporary files and orphaned directories.

Prevents disk bloat and strictly verifies that deletion targets do not escape
the configured base temporary directory.
"""

import shutil
from pathlib import Path
from typing import Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def is_safe_subdirectory(target: Path, base: Path) -> bool:
    """Check if target path is strictly inside base directory."""
    try:
        resolved_target = target.resolve()
        resolved_base = base.resolve()
        return (
            resolved_target != resolved_base
            and resolved_base in resolved_target.parents
        )
    except Exception:
        return False


def clean_job_directory(job_dir: Path, base_dir: Optional[Path] = None) -> bool:
    """Safely remove a specific job temporary directory."""
    base = base_dir or settings.temp_dir
    if not job_dir.exists():
        return True

    if not is_safe_subdirectory(job_dir, base):
        logger.error(
            f"Security violation: Refusing to delete path '{job_dir}' outside base '{base}'"
        )
        return False

    try:
        shutil.rmtree(job_dir, ignore_errors=True)
        logger.debug(f"Successfully cleaned job directory: {job_dir}")
        return True
    except Exception as e:
        logger.warning(f"Failed to remove job directory {job_dir}: {e}")
        return False


def startup_cleanup(base_dir: Optional[Path] = None) -> int:
    """Clean all leftover temporary files and directories on bot startup."""
    base = base_dir or settings.temp_dir
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return 0

    cleaned_count = 0
    try:
        for item in base.iterdir():
            if item.is_dir() and is_safe_subdirectory(item, base):
                shutil.rmtree(item, ignore_errors=True)
                cleaned_count += 1
            elif item.is_file():
                item.unlink(missing_ok=True)
                cleaned_count += 1
        logger.info(f"Startup cleanup completed: removed {cleaned_count} leftover items in {base}.")
    except Exception as e:
        logger.warning(f"Error during startup cleanup of {base}: {e}")

    return cleaned_count
