import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# === Пути ===
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"
load_dotenv(dotenv_path=BASE_DIR / ".env")

# === Логгер ===
logger = logging.getLogger(__name__)

# === Авторизованные номера ===
def get_authorized_numbers():
    return {
        num.strip()
        for num in os.getenv("AUTHORIZED_NUMBERS", "").split(",")
        if num.strip()
    }

AUTHORIZED_NUMBERS = get_authorized_numbers()

if not AUTHORIZED_NUMBERS:
    logger.warning("⚠️ AUTHORIZED_NUMBERS пуст. Ни один пользователь не сможет авторизоваться.")

# === Токен ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env!")

if not BOT_TOKEN.startswith(("5", "6", "1")):  # просто как базовая проверка
    logger.warning("⚠️ BOT_TOKEN выглядит подозрительно. Проверь значение в .env")

# === Админы ===
ADMIN_IDS = []
for admin in os.getenv("ADMINS", "").split(","):
    admin = admin.strip()
    if not admin:
        continue
    try:
        ADMIN_IDS.append(int(admin))
    except ValueError:
        logger.warning(f"⚠️ ADMIN_IDS: неверный ID «{admin}» — пропущен")

if not ADMIN_IDS:
    logger.warning("⚠️ Список админов пуст. Никто не сможет подтверждать доступ.")

# === Антифлуд ===
try:
    FLOOD_LIMIT = int(os.getenv("FLOOD_LIMIT", 5))
    FLOOD_PERIOD = int(os.getenv("FLOOD_PERIOD", 10))
    FLOOD_BLOCK_TIME = int(os.getenv("FLOOD_BLOCK_TIME", 15))
except ValueError as e:
    raise ValueError(f"❌ Ошибка в настройках антифлуда: {e}")

if FLOOD_LIMIT <= 0:
    raise ValueError("❌ FLOOD_LIMIT должен быть больше 0")

if FLOOD_PERIOD <= 0:
    raise ValueError("❌ FLOOD_PERIOD должен быть больше 0")

if FLOOD_BLOCK_TIME < 0:
    raise ValueError("❌ FLOOD_BLOCK_TIME не может быть отрицательным")

# === Блокировка при ошибках авторизации ===
try:
    BLOCK_DURATION = int(os.getenv("BLOCK_DURATION", 300))
except ValueError:
    raise ValueError("❌ BLOCK_DURATION должен быть целым числом")

if BLOCK_DURATION < 10:
    logger.warning("⚠️ BLOCK_DURATION слишком мал. Рекомендуется >= 60 секунд")

# === БД ===
DB_FILE = os.getenv("DB_FILE", "bot_data.db")
