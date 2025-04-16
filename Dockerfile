# Используем официальный минимальный Python-образ
FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем зависимости
COPY requirements.txt /app/requirements.txt

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер
COPY . /app
 HEAD

# Копируем .env внутрь образа
COPY .env /app/.env
 🚀 Initial commit: clean and secure
# Переменная, чтобы вывод логов был виден сразу
ENV PYTHONUNBUFFERED=1

# Команда запуска бота
CMD ["python", "bot.py"]
