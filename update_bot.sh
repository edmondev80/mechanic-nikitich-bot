#!/bin/bash

echo "🔄 Обновление кода из Git..."
git pull origin main || { echo "❌ Ошибка при git pull"; exit 1; }

echo "🛑 Остановка текущего контейнера..."
docker compose down || { echo "❌ Не удалось остановить контейнер"; exit 1; }

echo "⚙️ Сборка и запуск новой версии..."
docker compose up --build -d || { echo "❌ Не удалось запустить контейнер"; exit 1; }

echo "✅ Готово! Бот перезапущен в фоне."
