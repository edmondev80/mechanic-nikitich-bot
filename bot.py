import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    FLOOD_LIMIT,
    FLOOD_PERIOD,
    FLOOD_BLOCK_TIME,
    AUTHORIZED_NUMBERS,
)

if os.getenv("RUN_IN_DOCKER") != "1":
    print("🚫 Запуск запрещён! Используйте Docker.")
    sys.exit(1)

# Инициализация базы данных и функций
from db import init_db, clear_blocks, remove_expired_blocks
from utils import DATA_JSON, FLAT_DATA  # Только глобальные переменные

# Подключение роутеров
from handlers.menu import (
    router as menu_router,
    register_bot_instance,
    on_startup,
    read_json,
    flatten_json
)

from handlers.admin import router as admin_router  # Новый хендлер
from middlewares.flood_control import FloodControlMiddleware

# === Логирование ===
LOG_FILE = "bot.log"
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# === Проверка токена ===
if not BOT_TOKEN:
    logger.critical("❌ Не указан BOT_TOKEN в .env. Завершаем.")
    sys.exit(1)

# === Инициализация бота и диспетчера ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
register_bot_instance(bot)

storage = MemoryStorage()  # TODO: заменить на PostgreSQLStorage в будущем
dp = Dispatcher(storage=storage)
dp.startup.register(on_startup)

# === Подключение middleware и роутеров ===
dp.message.middleware(
    FloodControlMiddleware(
        limit=FLOOD_LIMIT,
        period=FLOOD_PERIOD,
        block_time=FLOOD_BLOCK_TIME,
        admin_ids=ADMIN_IDS
    )
)
dp.include_router(menu_router)
dp.include_router(admin_router)  # Подключаем /users

# === Фоновая задача: очистка блокировок ===
async def cleanup_expired_blocks():
    while True:
        try:
            remove_expired_blocks()
        except Exception as e:
            logger.exception(f"❌ Ошибка при удалении просроченных блокировок: {e}")
        await asyncio.sleep(300)

# === Основная логика ===
async def main():
    init_db() # Инициализация базы
    from config import get_authorized_numbers
    from db import remove_revoked_users

    AUTHORIZED_NUMBERS = get_authorized_numbers()
    removed_users = remove_revoked_users(AUTHORIZED_NUMBERS)
    if removed_users:
        for uid, num in removed_users:
            logger.info(f"🗑 Удалён пользователь {uid} с табельным номером {num} (удалён из .env)")

    clear_blocks()    # Чистим старые блокировки при старте
    asyncio.create_task(cleanup_expired_blocks())  # Фон. задача

    # Загрузка документации
    data_path = Path(__file__).parent / "data.json"
    try:
        loaded = await read_json(data_path)
        if not loaded:
            logger.critical("❌ Ошибка загрузки data.json. Завершаем.")
            sys.exit(1)

        DATA_JSON.clear()
        DATA_JSON.update(loaded)
        FLAT_DATA.clear()
        FLAT_DATA.extend(flatten_json(DATA_JSON))
        logger.info(f"📥 Загружено {len(FLAT_DATA)} записей из документации")
    except Exception as e:
        logger.exception(f"❌ Ошибка при чтении data.json: {e}")
        sys.exit(1)

    logger.info(f"✅ Авторизованные номера загружены: {len(AUTHORIZED_NUMBERS)}")

    try:
        logger.info("🚀 Бот запущен!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("🔒 Сессия Telegram API закрыта")

# === Точка входа ===
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        logger.info("🛑 Остановка по CancelledError — graceful shutdown.")
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем.")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка при запуске бота: {e}")
