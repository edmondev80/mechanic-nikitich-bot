import os
import logging

logger = logging.getLogger(__name__)

AUTHORIZED_NUMBERS = {num.strip() for num in os.getenv("AUTHORIZED_NUMBERS", "").split(",") if num.strip()}
DATA_JSON = {}
FLAT_DATA = []


from typing import TypeVar, Type, Callable

T = TypeVar("T")

def get_env(
    key: str,
    default: T = None,
    cast: Callable[[str], T] = str,
    required: bool = False
) -> T:
    """
    Умная загрузка из .env с приведением типа и логированием ошибок.

    :param key: Название переменной окружения.
    :param default: Значение по умолчанию, если переменная не найдена.
    :param cast: Функция приведения к типу (str, int, float, bool, list).
    :param required: Если True — будет исключение, если переменная не найдена.
    """
    value = os.getenv(key)

    if value is None:
        if required:
            raise ValueError(f"❌ Обязательная переменная {key} не найдена в .env")
        logging.warning(f"⚠️ Переменная {key} не найдена. Используется значение по умолчанию: {default}")
        return default

    try:
        if cast == bool:
            return value.lower() in ("1", "true", "yes", "on")  # для булевых
        if cast == list:
            return [x.strip() for x in value.split(",") if x.strip()]
        return cast(value)
    except Exception as e:
        logging.warning(f"⚠️ Ошибка при преобразовании переменной {key}: {e}. Значение: {value}")
        return default
