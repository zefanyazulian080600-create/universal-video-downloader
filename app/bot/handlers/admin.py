"""Admin monitoring and management handlers."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters.admin_filter import IsAdmin
from app.services.statistics import StatisticsService

router = Router(name="admin_router")


@router.message(Command("admin"), IsAdmin())
async def handle_admin(message: Message) -> None:
    """Provide administrative health, metrics, and storage report."""
    report = await StatisticsService.format_admin_report()
    await message.answer(text=report, parse_mode="HTML")
