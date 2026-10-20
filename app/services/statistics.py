"""System metrics, storage monitoring, and operational reporting service."""

import os
import platform
import shutil
import time
from typing import Any, Dict

from sqlalchemy import func, select

from app.config import settings
from app.database.models import DownloadJob, User
from app.database.repository import JobRepository
from app.database.session import get_db_session
from app.downloader.ffmpeg_service import FFmpegService
from app.jobs.manager import job_manager
from app.utils.filenames import format_duration, format_file_size

# Global startup timestamp
BOT_START_TIME = time.time()


class StatisticsService:
    """Collects and formats system health, resource, and operational metrics."""

    @staticmethod
    def get_uptime_seconds() -> float:
        """Seconds since bot started."""
        return time.time() - BOT_START_TIME

    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """Return disk usage for temporary directory."""
        try:
            total, used, free = shutil.disk_usage(str(settings.temp_dir))
            return {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "percent_used": (used / total) * 100.0 if total > 0 else 0.0,
            }
        except Exception:
            return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "percent_used": 0.0}

    @staticmethod
    async def get_dashboard_metrics() -> Dict[str, Any]:
        """Aggregate operational metrics across database, memory, and filesystem."""
        disk = StatisticsService.get_disk_usage()
        uptime_sec = StatisticsService.get_uptime_seconds()
        active_in_memory = job_manager.get_total_active_count()

        async with get_db_session() as session:
            db_stats = await JobRepository.get_global_stats(session)
            user_count_stmt = select(func.count(User.id))
            user_count = (await session.execute(user_count_stmt)).scalar() or 0

        ffmpeg_status = "Tersedia ✅" if FFmpegService().is_available() else "Tidak Ditemukan ⚠️"

        return {
            "uptime_seconds": uptime_sec,
            "formatted_uptime": format_duration(uptime_sec),
            "active_jobs": active_in_memory,
            "total_users": user_count,
            "total_jobs": db_stats["total_jobs"],
            "completed_jobs": db_stats["completed_jobs"],
            "failed_jobs": db_stats["failed_jobs"],
            "disk_free": format_file_size(disk["free_bytes"]),
            "disk_total": format_file_size(disk["total_bytes"]),
            "disk_percent": disk["percent_used"],
            "python_version": platform.python_version(),
            "os_name": f"{platform.system()} {platform.release()}",
            "ffmpeg_status": ffmpeg_status,
        }

    @staticmethod
    async def format_admin_report() -> str:
        """Format metrics into a clear Telegram admin message in Indonesian."""
        m = await StatisticsService.get_dashboard_metrics()
        lines = [
            "📊 <b>Statistik & Status Server Bot</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"⏱ <b>Uptime:</b> {m['formatted_uptime']}",
            f"👥 <b>Total Pengguna:</b> {m['total_users']}",
            f"🔄 <b>Unduhan Aktif:</b> {m['active_jobs']}",
            f"📥 <b>Total Job:</b> {m['total_jobs']}",
            f"✅ <b>Berhasil:</b> {m['completed_jobs']}",
            f"❌ <b>Gagal:</b> {m['failed_jobs']}",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"💾 <b>Sisa Disk:</b> {m['disk_free']} / {m['disk_total']} ({m['disk_percent']:.1f}% terpakai)",
            f"🎬 <b>FFmpeg:</b> {m['ffmpeg_status']}",
            f"🐍 <b>Python:</b> {m['python_version']}",
            f"💻 <b>Sistem:</b> {m['os_name']}",
        ]
        return "\n".join(lines)
