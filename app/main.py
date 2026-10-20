"""Main application entry point for Universal Telegram Video Downloader (LinkGrabber Bot).

Orchestrates dependency initialization, database schema creation, startup cleanup,
router registration, command menu setup, and graceful shutdown.
"""

import asyncio
import io
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot.handlers import admin, download, history, settings as bot_settings, start
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user_tracker import UserTrackerMiddleware
from app.config import settings
from app.database.repository import JobRepository
from app.database.session import close_db, get_db_session, init_db
from app.downloader.ffmpeg_service import FFmpegService
from app.jobs.cleanup import startup_cleanup
from app.jobs.queue import JobQueue
from app.utils.logging import get_logger, setup_logging

logger = get_logger("app.main")


async def setup_bot_commands(bot: Bot) -> None:
    """Register command menu in Telegram UI."""
    commands = [
        BotCommand(command="start", description="Mulai bot & buka menu utama"),
        BotCommand(command="help", description="Panduan penggunaan & info"),
        BotCommand(command="platforms", description="Daftar platform didukung"),
        BotCommand(command="settings", description="Pengaturan kualitas & format"),
        BotCommand(command="quality", description="Pintasan ubah kualitas default"),
        BotCommand(command="status", description="Status unduhan aktif milikmu"),
        BotCommand(command="cancel", description="Batalkan unduhan yang berjalan"),
        BotCommand(command="history", description="Riwayat unduhan terakhir"),
        BotCommand(command="about", description="Info versi & arsitektur bot"),
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands menu registered successfully.")
    except Exception as e:
        logger.warning(f"Could not register Telegram bot commands: {e}")


async def main() -> None:
    """Run bot application lifecycle."""
    # 1. Setup structured logging
    setup_logging(log_level=settings.log_level)
    logger.info("=================================================")
    logger.info("Starting Universal Video Downloader Bot (LinkGrabber)")
    logger.info("=================================================")

    # 2. Check token presence
    if not settings.bot_token or settings.bot_token.strip() in ("", "your_telegram_bot_token_here"):
        logger.critical(
            "FATAL: BOT_TOKEN is missing or not configured! "
            "Please copy .env.example to .env and provide a valid Telegram Bot Token from @BotFather."
        )
        sys.exit(1)

    # 3. Ensure required directories
    settings.ensure_directories()

    # 4. Perform startup cleanup of orphaned temporary files
    cleaned = startup_cleanup()
    logger.info(f"Cleaned {cleaned} leftover files in temporary directory.")

    # 5. Initialize database tables
    await init_db()

    # 6. Reset any interrupted active jobs from previous runs
    async with get_db_session() as session:
        interrupted = await JobRepository.reset_interrupted_jobs(session)
        if interrupted > 0:
            logger.info(f"Marked {interrupted} interrupted jobs from previous shutdown as failed.")

    # 7. Check FFmpeg availability
    ffmpeg = FFmpegService()
    if ffmpeg.is_available():
        logger.info("FFmpeg and ffprobe detected and operational.")
    else:
        logger.warning(
            "FFmpeg or ffprobe NOT found on system PATH. "
            "Stream merging and thumbnail generation may be restricted."
        )

    # 8. Initialize Bot and Dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # 9. Initialize and inject JobQueue
    job_queue = JobQueue(bot=bot)
    download.set_job_queue(job_queue)

    # 10. Register Middlewares
    dp.message.middleware(ThrottlingMiddleware(limit=settings.user_rate_limit))
    dp.callback_query.middleware(ThrottlingMiddleware(limit=settings.user_rate_limit))

    dp.message.middleware(UserTrackerMiddleware())
    dp.callback_query.middleware(UserTrackerMiddleware())

    # 11. Register Routers
    dp.include_router(start.router)
    dp.include_router(bot_settings.router)
    dp.include_router(history.router)
    dp.include_router(admin.router)
    dp.include_router(download.router)  # Handles text/URLs

    # 12. Register Commands Menu
    await setup_bot_commands(bot)

    # 13. Start Long Polling
    logger.info("LinkGrabber Bot is now listening for Telegram updates...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=True,
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Performing graceful shutdown...")
        await close_db()
        await bot.session.close()
        logger.info("LinkGrabber Bot stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
