from aiogram import Router, types
from aiogram.filters import Command
from config import ADMIN_IDS
from db import get_last_users
from aiogram.types import FSInputFile
from db import export_users_to_excel

router = Router(name="admin")

import logging
logger = logging.getLogger(__name__) # Тоже корневой логгер

@router.message(Command("users"))
async def show_last_users(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    users = get_last_users(limit=10)
    if not users:
        await message.answer("👥 Нет авторизованных пользователей.")
        return

    lines = []
    for uid, number, name, auth_time in users:
        lines.append(
            f"<b>{name}</b>\n"
            f"ID: <code>{uid}</code>\n"
            f"Номер: <code>{number}</code>\n"
            f"🕒 {auth_time}\n"
        )

    await message.answer("📋 <b>Последние пользователи:</b>\n\n" + "\n".join(lines))

@router.message(Command("export"))
async def export_users(message: types.Message):
    if str(message.from_user.id) not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    filename = export_users_to_excel()
    await message.answer_document(
        FSInputFile(path=filename),
        caption="📁 Экспорт пользователей в Excel"
    )
