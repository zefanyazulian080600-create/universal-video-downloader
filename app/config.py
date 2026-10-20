"""Configuration management using Pydantic Settings.

Reads settings from environment variables or .env file with validation
and safe defaults. Sensitive values (tokens) are masked in representations.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration schema."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot Token (mandatory for running the bot)
    bot_token: str = Field(
        default="",
        alias="BOT_TOKEN",
        description="Telegram bot token obtained from @BotFather",
    )

    # Bot Owner / Admin ID
    bot_owner_id: int = Field(
        default=0,
        alias="BOT_OWNER_ID",
        description="Telegram user ID of the primary administrator",
    )

    # Database URL (SQLAlchemy 2.x async)
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db",
        alias="DATABASE_URL",
        description="Async database connection string",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # Temporary directory for media processing
    temp_dir: Path = Field(
        default=Path("./downloads"),
        alias="TEMP_DIR",
        description="Base temporary storage directory for downloads",
    )

    # Storage and Size Limits
    max_upload_mb: float = Field(
        default=50.0,
        alias="MAX_UPLOAD_MB",
        description="Maximum Telegram upload size in MB (50 MB standard, up to 2000 MB with local Bot API)",
    )

    max_download_mb: float = Field(
        default=200.0,
        alias="MAX_DOWNLOAD_MB",
        description="Maximum download file size from source platform in MB",
    )

    max_video_duration_seconds: int = Field(
        default=1800,
        alias="MAX_VIDEO_DURATION_SECONDS",
        description="Maximum video duration allowed in seconds (e.g. 1800s = 30 min)",
    )

    # Concurrency and Queue
    max_concurrent_downloads: int = Field(
        default=3,
        alias="MAX_CONCURRENT_DOWNLOADS",
        description="Global maximum concurrent download operations",
    )

    max_jobs_per_user: int = Field(
        default=2,
        alias="MAX_JOBS_PER_USER",
        description="Maximum concurrent active jobs per single Telegram user",
    )

    # Timeouts
    metadata_timeout_seconds: int = Field(
        default=30,
        alias="METADATA_TIMEOUT_SECONDS",
        description="Timeout for inspecting URL metadata",
    )

    download_timeout_seconds: int = Field(
        default=600,
        alias="DOWNLOAD_TIMEOUT_SECONDS",
        description="Timeout for downloading media stream",
    )

    # Features
    enable_ffmpeg: bool = Field(
        default=True,
        alias="ENABLE_FFMPEG",
        description="Whether to use FFmpeg/ffprobe for stream merging & probing",
    )

    enable_compression: bool = Field(
        default=False,
        alias="ENABLE_COMPRESSION",
        description="Whether to attempt FFmpeg compression if file exceeds max_upload_mb",
    )

    job_retention_days: int = Field(
        default=7,
        alias="JOB_RETENTION_DAYS",
        description="Retention period in days for completed/failed jobs in database",
    )

    user_rate_limit: int = Field(
        default=10,
        alias="USER_RATE_LIMIT",
        description="Maximum requests per minute per user to prevent flooding",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        val = v.upper().strip()
        if val not in valid_levels:
            return "INFO"
        return val

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def max_download_bytes(self) -> int:
        """Maximum download size in bytes."""
        return int(self.max_download_mb * 1024 * 1024)

    def is_admin(self, user_id: int) -> bool:
        """Check if given Telegram user is administrator."""
        return self.bot_owner_id > 0 and user_id == self.bot_owner_id

    def ensure_directories(self) -> None:
        """Ensure required operational directories exist."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        # Also ensure data and logs directories exist
        Path("./data").mkdir(parents=True, exist_ok=True)
        Path("./logs").mkdir(parents=True, exist_ok=True)


# Global settings singleton
settings = Settings()
