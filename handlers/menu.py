import re
import asyncio
import logging
import html
import os
import bcrypt
from datetime import datetime
from functools import wraps
from aiogram import types, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import get_authorized_numbers
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    CallbackQuery
)
from dotenv import load_dotenv
import aiofiles
import json
from pathlib import Path
from db import (
    is_authorized, add_user, is_number_taken, is_same_user,
    add_block, remove_block, is_blocked, get_last_users, get_user_number
)

from db import (
    is_authorized, add_user, is_number_taken, is_same_user,
    add_block, remove_block, is_blocked, get_last_users
)
from config import BOT_TOKEN, AUTHORIZED_NUMBERS, ADMIN_IDS, BLOCK_DURATION, BASE_DIR
from utils import DATA_JSON, FLAT_DATA
from middlewares.auth import auth_required


router = Router()
logger = logging.getLogger(__name__)

bot_instance = None

def register_bot_instance(bot):
    global bot_instance
    bot_instance = bot

class MenuState(StatesGroup):
    path = State()
    authorized = State()
    searching = State()
    waiting_for_selection = State()

auth_attempts = {}
MAX_AUTH_ATTEMPTS = 3
INACTIVITY_TIMEOUT = 600
LAST_ACTIVE = {}

SYNONYMS = {
    "заправка": ["зарядка", "дозаправка"],
    "проверка": ["контроль", "диагностика", "испытание"],
    "очистка": ["чистка", "мойка"],
    "демонтаж": ["монтаж", "замена", "снятие", "установка"],
}

def escape_html(text: str) -> str:
    return html.escape(text)

def flatten_json(d, path=None):
    path = path or []
    flat = []
    if isinstance(d, dict):
        for k, v in d.items():
            flat.extend(flatten_json(v, path + [k]))
    else:
        flat.append({"категория": " > ".join(path), "путь": path, "ссылка": str(d)})
    return flat

def generate_back_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад"), KeyboardButton(text="🏠 Главное меню")]],
        resize_keyboard=True
    )

def generate_menu(current_data, is_root=True):
    buttons = []
    if is_root:
        buttons.append([KeyboardButton(text="🔍 Поиск документации")])
    for key in sorted(current_data):
        if not key.startswith("_"):
            buttons.append([KeyboardButton(text=key)])
    if not is_root:
        buttons.append([KeyboardButton(text="⬅ Назад"), KeyboardButton(text="🏠 Главное меню")])
    buttons.append([KeyboardButton(text="🚪 Выйти")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_node_from_path(path_list):
    current_node = DATA_JSON
    for key in path_list:
        if isinstance(current_node, dict) and key in current_node:
            current_node = current_node[key]
        else:
            return None
    return current_node

def expand_query(query):
    query = query.lower().strip()
    terms = set([query])
    for key, synonyms in SYNONYMS.items():
        if query == key or query in synonyms:
            terms.add(key)
            terms.update(synonyms)
    return terms

def search_documents(query):
    search_terms = expand_query(query)
    result_paths = {}
    for entry in FLAT_DATA:
        entry_text = f"{entry['категория']} {entry['ссылка']}".lower()
        if any(term in entry_text for term in search_terms):
            key = entry["путь"][1] if len(entry["путь"]) > 1 else entry["путь"][0]
            result_paths[key] = entry["путь"][:2]
    return result_paths

def log_login_attempt(user_id, full_name, number, status):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | LOGIN ATTEMPT | user_id={user_id} | full_name={full_name} | number={number} | status={status}\n"
    with open("login_attempts.log", "a", encoding="utf-8") as f:
        f.write(line)
    logger.info(line.strip())

def log_auth_block(user_id, full_name, number, attempts):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | AUTH BLOCK | user_id={user_id} | full_name={full_name} | number={number} | attempts={attempts}\n"
    with open("auth_blocks.log", "a", encoding="utf-8") as f:
        f.write(line)
    logger.warning(line.strip())

def log_admin_violation(user_id, full_name, command):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | ADMIN VIOLATION | user_id={user_id} | full_name={full_name} | tried: {command}\n"
    with open("admin_violations.log", "a", encoding="utf-8") as f:
        f.write(line)
    logger.warning(line.strip())

async def read_json(file_path: str) -> dict:
    try:
        async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
            contents = await f.read()
        return json.loads(contents)
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path}: {e}")
        return {}

def log_access_request(user_id: int, full_name: str, number: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"{timestamp} | ACCESS REQUEST | user_id={user_id} | "
        f"full_name={full_name} | number={number}\n"
    )
    with open("access_requests.log", "a", encoding="utf-8") as f:
        f.write(line)
    logger.info(line.strip())


logger = logging.getLogger(__name__)

import bcrypt

def check_still_authorized(user_id: int) -> bool:
    from db import get_user_number
    number_hash = get_user_number(user_id)

    if not number_hash:
        return False

    for number in AUTHORIZED_NUMBERS:
        if bcrypt.checkpw(number.encode(), number_hash.encode()):
            return True

    return False

@router.callback_query(F.data.startswith("deny_number:"))
async def handle_deny_number(callback: CallbackQuery):
    try:
        _, user_id = callback.data.split(":")
        user_id = int(user_id)

        await callback.answer("🚫 Отклонено")

        await callback.message.edit_text("❌ Запрос отклонён.")

        try:
            await bot_instance.send_message(
                chat_id=user_id,
                text="❌ Ваш запрос на доступ был отклонён администратором."
            )
        except Exception as e:
            logger.warning(f"[NOTIFY DENY FAIL] {e}")

    except Exception as e:
        logger.exception(f"[DENY NUMBER FAIL] {e}")
        await callback.answer("⚠️ Ошибка при отклонении.")


@router.callback_query(F.data.startswith("add_number:"))
async def handle_add_number(callback: CallbackQuery):
    try:
        _, user_id, number = callback.data.split(":")
        user_id = int(user_id)
        number = number.strip()

        env_path = Path(BASE_DIR) / ".env"

        if not env_path.exists():
            await callback.answer("❌ .env не найден")
            return

        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        found = False
        for line in lines:
            if line.startswith("AUTHORIZED_NUMBERS="):
                found = True
                existing = line.strip().split("=", 1)[1]
                nums = [x.strip() for x in existing.split(",") if x.strip()]
                if number not in nums:
                    nums.append(number)
                new_lines.append(f'AUTHORIZED_NUMBERS={" ,".join(nums)}\n')
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f'AUTHORIZED_NUMBERS={number}\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        load_dotenv(dotenv_path=env_path, override=True)
        AUTHORIZED_NUMBERS.add(number)

        await callback.answer("✅ Добавлено!")
        await callback.message.edit_text(
            f"✅ Табельный номер <code>{number}</code> добавлен в список.",
            parse_mode="HTML"
        )

        try:
            await bot_instance.send_message(
                chat_id=user_id,
                text="✅ Вам открыт доступ к боту. Введите /start для входа."
            )
        except Exception as e:
            logger.warning(f"[NOTIFY USER FAIL] {e}")

    except Exception as e:
        logger.exception(f"[ADD NUMBER FAIL] {e}")
        await callback.answer("⚠️ Ошибка при добавлении.")



def admin_only(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id not in ADMIN_IDS:
            if is_blocked(user_id):
                await message.answer("⛔ Вы временно заблокированы.")
                return
            await handle_admin_violation(user_id, message.from_user.full_name, message.text)
            return
        await handler(message, *args, **kwargs)
    return wrapper

async def handle_admin_violation(user_id: int, full_name: str, command: str):
    full_name = escape_html(full_name)
    command = escape_html(command)
    log_admin_violation(user_id, full_name, command)

    unblock_time = int(datetime.now().timestamp()) + BLOCK_DURATION
    add_block(user_id, unblock_time)

    try:
        for admin_id in ADMIN_IDS:
            await bot_instance.send_message(
                admin_id,
                f"🚫 <b>Блокировка:</b> Пользователь {full_name} ({user_id}) "
                f"попытался использовать <code>{command}</code> и был временно заблокирован.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"[ADMIN BLOCK ALERT] Не удалось уведомить админов: {e}")

    try:
        await bot_instance.send_message(
            user_id,
            "⛔ Вы временно заблокированы за попытку доступа к административной команде.\n\n"
            "🔓 Блокировка снимется через 5 минут."
        )
    except Exception:
        pass

    await asyncio.sleep(BLOCK_DURATION)
    remove_block(user_id)

async def delete_previous_message(message: types.Message):
    try:
        await bot_instance.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
    except Exception as e:
        logger.warning(f"[DELETE ERROR] Не удалось удалить сообщение: {e}")

async def read_log_file(path: str, empty_message: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-10:]) if lines else empty_message
    except FileNotFoundError:
        return empty_message
    except Exception as e:
        logger.error(f"[LOG READ ERROR] {path}: {e}")
        return "⚠️ Ошибка при чтении журнала."

@router.message(Command("help"))
async def help_command(message: types.Message):
    logger.info(f"[HELP] Пользователь {message.from_user.id} запросил помощь")
    await message.answer(
        "🛠 <b>Доступные команды:</b>\n"
        "/start — Главное меню\n"
        "/help — Подсказка по функциям\n"
        "/search — Поиск по документации\n"
        "/reset — Сброс авторизации\n\n"
        "💬 <i>Для доступа к функциям просто выберите раздел из меню или воспользуйтесь поиском.</i>",
        parse_mode="HTML"
    )

@router.message(Command("search"))
@auth_required
async def start_search(message: types.Message, state: FSMContext):
    await state.set_state(MenuState.searching)
    await message.answer("🔎 Введите ключевое слово для поиска:", reply_markup=ReplyKeyboardRemove())


@router.message(Command("reset"))
@auth_required
async def reset_auth(message: types.Message, state: FSMContext):
    from db import remove_user
    user_id = message.from_user.id
    remove_user(user_id)
    await state.clear()
    await message.answer("🔁 Авторизация сброшена.\n🔐 Введите табельный номер повторно:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(MenuState.authorized)


@router.message(Command("admin"))
@admin_only
async def admin_panel(message: types.Message):
    await message.answer(
        "👨‍🔧 <b>Админ-панель</b>:\n"
        "/log — Последние попытки входа\n"
        "/violations — Попытки доступа к админ-командам\n"
        "/clear_log — Очистить лог входа\n"
        "/reset — Сброс авторизации\n"
        "/start — Главное меню",
        parse_mode="HTML"
    )

@router.message(Command("log"))
@admin_only
async def show_login_log(message: types.Message):
    users = get_last_users()
    if not users:
        await message.answer("📭 Журнал пуст.")
        return

    lines = [
        f"👤 <b>{u[2]}</b>\nID: <code>{u[0]}</code>\nНомер: {u[1]}\n⏱ {u[3]}"
        for u in users
    ]
    await message.answer("\n\n".join(lines), parse_mode="HTML")


@router.message(Command("violations"))
@admin_only
async def show_admin_violations(message: types.Message):
    text = await read_log_file("admin_violations.log", "📭 Нарушений не зафиксировано.")
    await message.answer(f"<pre>{escape_html(text)}</pre>", parse_mode="HTML")

@router.message(Command("clear_log"))
@admin_only
async def clear_login_log(message: types.Message):
    import os
    try:
        if os.path.exists("login_attempts.log"):
            os.remove("login_attempts.log")
            await message.answer("🧹 Лог входа очищен.")
        else:
            await message.answer("📭 Лог уже пуст.")
    except Exception as e:
        logger.error(f"[CLEAR LOG ERROR] Не удалось удалить лог: {e}")
        await message.answer("⚠️ Ошибка при удалении лога.")

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    try:
        for i in range(1, 100):
            await bot_instance.delete_message(chat_id=message.chat.id, message_id=message.message_id - i)
    except Exception:
        pass

    user_id = message.from_user.id
    full_name = message.from_user.full_name

    if is_authorized(user_id):
        if not check_still_authorized(user_id):
            from db import remove_user
            remove_user(user_id)
            await state.clear()
            await message.answer(
                "⛔ Ваш доступ был отозван администратором.\n"
                "🔐 Введите табельный номер повторно для запроса доступа:",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(MenuState.authorized)
            return

        await state.set_state(MenuState.path)
        await message.answer(
            escape_html("👋 механик Никитич рад тебя видеть снова!\nВыберите раздел:"),
            parse_mode="HTML",
            reply_markup=generate_menu(DATA_JSON)
        )
    else:
        await state.clear()
        await state.set_state(MenuState.authorized)
        await message.answer("🔐 Введите табельный номер для входа:", reply_markup=ReplyKeyboardRemove())
        await message.answer("ℹ️ Напишите /help, если вам нужно больше информации о командах.")

@router.message(MenuState.path)
async def navigate_menu(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Неверный формат сообщения. Отправьте текст.")
        return
    
    user_text = message.text.strip()
    user_text_lower = user_text.lower()
    if user_text in ["/search", "search", "/reset", "reset"]:
        await message.answer("⚠️ Для использования команды используйте /search или /reset, а не обычный текст.")
        return

    current_path = (await state.get_data()).get("path", [])

    if user_text_lower in ["🚪 выйти", "выйти"]:
        await state.clear()
        await message.answer(
            "🔒 Вы вышли из системы.\n/start — чтобы войти снова",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"  
        )
        return

    elif user_text_lower in ["⬅ назад", "назад"]:
        if current_path:
            current_path.pop()
            await state.update_data(path=current_path)
        current_node = get_node_from_path(current_path)
        await message.answer("📂 Назад", reply_markup=generate_menu(current_node, is_root=not current_path))
        return

    elif user_text_lower in ["🏠 главное меню", "главное меню"]:
        await state.update_data(path=[])
        await message.answer("🏠 Главное меню", reply_markup=generate_menu(DATA_JSON))
        return

    if user_text == "🔍 Поиск документации":
        await state.set_state(MenuState.searching)
        await message.answer("🔎 Введите ключевое слово для поиска:", reply_markup=ReplyKeyboardRemove())
        return

    current_node = get_node_from_path(current_path)
    matching_key = next((key for key in current_node if key.lower() == user_text), None)
    if matching_key:
        user_text = matching_key
        # Проверка подписки для раздела "Ресеты"
            # Проверка подписки на раздел "Ресеты"
        if user_text.lower() == "ресеты":
            from config import ADMIN_IDS
            from db import is_subscribed
            if message.from_user.id not in ADMIN_IDS and not is_subscribed(message.from_user.id):
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                subscription_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Написать админу", url="https://t.me/eduard_admin")]
                ])

                await bot_instance.send_photo(
                    chat_id=message.chat.id,
                    photo=types.FSInputFile("qr.png"),
                    caption=(
                        "🔒 <b>Раздел «Ресеты» доступен только по подписке</b>\n\n"
                        "💳 <b>Стоимость:</b> 199₽ (разовый платеж)\n\n"
                        "📷 <b>Отсканируйте QR-код выше и оплатите через СБП</b>\n\n"
                        "📝 В комментарии к переводу укажите табельный номер или Telegram username.\n\n"
                        "После оплаты нажмите кнопку ниже, чтобы сообщить администратору."
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔑 Написать админу", url="https://t.me/VirtuozEV")]
                    ])
                )

                return

        current_path.append(user_text)
        await state.update_data(path=current_path)
        next_node = current_node[user_text]

        if isinstance(next_node, dict): 
            description = next_node.get("_описание")
            submenu = {k: v for k, v in next_node.items() if not k.startswith("_")}

            if description and not submenu:
                # Только описание, без вложений — выводим и выходим
                await message.answer(f"📄 <b>Описание:</b>\n\n{escape_html(description)}", parse_mode="HTML", reply_markup=generate_back_menu())
                return

            if description:
                await message.answer(f"📄 <b>Описание:</b>\n\n{escape_html(description)}", parse_mode="HTML")

            if submenu:
                await message.answer(
                    f"📁 Раздел: <b>{escape_html(user_text)}</b>",
                    parse_mode="HTML",
                    reply_markup=generate_menu(submenu, is_root=False)
                )
            else:
                await message.answer(
                    f"📄 <b>Описание:</b>\n\n{escape_html(str(next_node))}",
                    parse_mode="HTML",
                    reply_markup=generate_back_menu()
                )

        else:
            # Если значение — словарь и в нём есть _описание
            if isinstance(next_node, dict) and "_описание" in next_node:
                description = next_node["_описание"]
            else:
                description = str(next_node)

            await message.answer(
                f"📄 <b>Описание:</b>\n\n{escape_html(description)}",
                parse_mode="HTML",
                reply_markup=generate_back_menu()
            )

@router.message(MenuState.authorized)
async def handle_authorization(message: types.Message, state: FSMContext):
    if message.text.startswith("/"):
        await message.answer("⚠️ Пожалуйста, введите только табельный номер.")
        return

    start_time = datetime.now()
    number = message.text.strip()
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    logger.info(f"[TIME] START handle_authorization | {start_time}")

    if is_blocked(user_id):
        logger.info(f"[TIME] BLOCKED | {datetime.now() - start_time}")
        await message.answer("⛔ Вы временно заблокированы за превышение попыток входа. Попробуйте позже.")
        return

    if number in AUTHORIZED_NUMBERS:
        try:
            add_user(user_id, number, full_name)
            logger.info(f"[TIME] USER ADDED TO DB | {datetime.now() - start_time}")
            log_login_attempt(user_id, full_name, number, "accepted")
            auth_attempts.pop(user_id, None)
            await state.set_state(MenuState.path)
            await message.answer(
                f"✅ Авторизация успешна! Добро пожаловать {escape_html(full_name)} к механику Никитичу 🔧✨.",
                parse_mode="HTML",
                reply_markup=generate_menu(DATA_JSON)
            )
            logger.info(f"[TIME] SUCCESS RESPONSE SENT | {datetime.now() - start_time}")
            return
        except ValueError as e:
            warning = await message.answer(str(e))
            logger.info(f"[TIME] DUPLICATE NUMBER ERROR | {datetime.now() - start_time}")
            log_login_attempt(user_id, full_name, number, "rejected: duplicate number")
            await asyncio.sleep(5)
            try:
                await warning.delete()
                await message.delete()
            except Exception:
                pass
            await message.answer("🔐 Введите табельный номер для входа ещё раз:")
            return


    # Если номер не найден
    count = auth_attempts.get(user_id, 0) + 1
    auth_attempts[user_id] = count
    log_login_attempt(user_id, full_name, number, f"denied (attempt {count})")

    if count >= MAX_AUTH_ATTEMPTS:
        unblock_time = int(datetime.now().timestamp()) + BLOCK_DURATION
        add_block(user_id, unblock_time)
        auth_attempts.pop(user_id, None)
        log_auth_block(user_id, full_name, number, count)

        logger.info(f"[TIME] BLOCKED USER | {datetime.now() - start_time}")

        if bot_instance:
            for admin_id in ADMIN_IDS:
                try:
                    await bot_instance.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🚫 <b>Блокировка по логину</b>\n\n"
                            f"<b>Имя:</b> {escape_html(full_name)}\n"
                            f"<b>ID:</b> <code>{user_id}</code>\n"
                            f"<b>Введённый номер:</b> <code>{escape_html(number)}</code>\n"
                            f"<b>Попытки:</b> {count}\n"
                            f"⏱ Блокировка на {BLOCK_DURATION // 60} минут(ы)"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"[ADMIN ALERT] Не удалось уведомить админа {admin_id}: {e}")

        await message.answer(
            f"⛔ Превышено число попыток входа.\nВы временно заблокированы на {BLOCK_DURATION // 60} минут(ы)."
        )
        return

    # Запрос на доступ
    await message.answer("📨 Ваш запрос на доступ отправлен администратору.\n⏳ Пожалуйста, дождитесь подтверждения.")

    logger.info(f"[TIME] ACCESS REQUEST SENT | {datetime.now() - start_time}")

    if bot_instance:
        for admin_id in ADMIN_IDS:
            try:
                await bot_instance.send_message(
                    chat_id=admin_id,
                    text=(
                        f"📥 <b>Запрос на доступ</b>\n\n"
                        f"<b>Имя:</b> {escape_html(full_name)}\n"
                        f"<b>ID:</b> <code>{user_id}</code>\n"
                        f"<b>Введённый номер:</b> <code>{escape_html(number)}</code>\n\n"
                        f"⬇️ Добавьте в список:"
                    ),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Добавить", callback_data=f"add_number:{user_id}:{number}"),
                            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_number:{user_id}")
                        ]
                    ]),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"[ACCESS REQUEST] Ошибка отправки админу: {e}")

    logger.info(f"[TIME] FINISHED handle_authorization | {datetime.now() - start_time}")

   
    log_access_request(user_id, full_name, number)

    return

def check_still_authorized(user_id: int) -> bool:
    from db import get_user_number
    number = get_user_number(user_id)
    return number in AUTHORIZED_NUMBERS

@router.message(MenuState.searching)
async def handle_search(message: types.Message, state: FSMContext):
    user_text = message.text.strip().lower()
    if user_text in ["/search", "search", "/reset", "reset"]:
        await message.answer("⚠️ Вы уже находитесь в режиме поиска. Введите ключевое слово или нажмите 'Назад'.")
        return

    query = message.text.strip()
    matches = search_documents(query)

    if not matches:
        await message.answer("❌ По вашему запросу ничего не найдено. Попробуйте другое слово.")
        return

    await state.set_state(MenuState.waiting_for_selection)
    await state.update_data(search_results=matches)

    buttons = [[KeyboardButton(text=key)] for key in sorted(matches)]
    buttons.append([KeyboardButton(text="⬅ Назад"), KeyboardButton(text="🏠 Главное меню")])
    await message.answer("🔍 Найдено:\nВыберите раздел:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))


@router.message(MenuState.waiting_for_selection)
async def handle_search_selection(message: types.Message, state: FSMContext):
    user_text = message.text
    data = await state.get_data()

    if user_text in data.get("search_results", {}):
        path = data["search_results"][user_text]
        await state.update_data(path=path)
        await state.set_state(MenuState.path)
        current_node = get_node_from_path(path)
        await message.answer(
            f"📁 Перейдено к: <b>{escape_html(user_text)}</b>",
            parse_mode="HTML",
            reply_markup=generate_menu(current_node, is_root=False)
        )
    elif user_text == "⬅ Назад":
        await state.set_state(MenuState.path)
        await message.answer("🔙 Назад в меню", reply_markup=generate_menu(DATA_JSON))
    elif user_text == "🏠 Главное меню":
        await state.update_data(path=[])
        await state.set_state(MenuState.path)
        await message.answer("🏠 Главное меню", reply_markup=generate_menu(DATA_JSON))
    else:
        await message.answer("❗ Раздел не найден. Пожалуйста, выберите из списка.")

__all__ = [
    "router",
    "register_bot_instance",
    "on_startup"
]

INACTIVITY_TIMEOUT = 600  # 10 минут
LAST_ACTIVE = {}

async def auto_logout_checker():
    while True:
        now = datetime.now()
        for user_id, last_active in list(LAST_ACTIVE.items()):
            if (now - last_active).total_seconds() > INACTIVITY_TIMEOUT:
                if is_authorized(user_id):
                    remove_block(user_id)
                    LAST_ACTIVE.pop(user_id)
        await asyncio.sleep(60)

async def on_startup(bot):
    asyncio.create_task(auto_logout_checker())

