from aiogram import types
from functools import wraps
from db import is_authorized

def auth_required(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        if not is_authorized(message.from_user.id):
            await message.answer("⛔ Доступ запрещён. Пожалуйста, авторизуйтесь.")
            return
        return await handler(message, *args, **kwargs)
    return wrapper
