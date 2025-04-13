import time
import logging
from collections import defaultdict
from aiogram import BaseMiddleware, types
from typing import Callable, Dict, Awaitable

logger = logging.getLogger(__name__)

class FloodControlMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 5, period: int = 10, block_time: int = 15, admin_ids=None):
        self.limit = limit
        self.period = period
        self.block_time = block_time
        self.user_messages: Dict[int, list] = defaultdict(list)
        self.blocked_until: Dict[int, float] = {}
        self.admin_ids = {int(a) for a in admin_ids} if admin_ids else set()

    async def __call__(self, handler: Callable[[types.Message, Dict], Awaitable], event: types.Message, data: Dict):
        user_id = event.from_user.id
        now = time.time()

        if user_id in self.admin_ids:
            return await handler(event, data)

        # Блокировка активна?
        if user_id in self.blocked_until and now < self.blocked_until[user_id]:
            return  # Молча игнорируем

        # Очистка старых сообщений
        timestamps = [t for t in self.user_messages[user_id] if now - t <= self.period]
        timestamps.append(now)
        self.user_messages[user_id] = timestamps

        # Проверка лимита
        if len(timestamps) > self.limit:
            self.blocked_until[user_id] = now + self.block_time
            logger.warning(
                f"[FLOOD] User {user_id} заблокирован на {self.block_time} секунд (лимит {self.limit}/{self.period}s)"
            )
            await event.answer("🚫 Слишком много сообщений! Вы временно заблокированы.")
            return

        return await handler(event, data)
