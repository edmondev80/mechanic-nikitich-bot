# admin_tool.py
from db import add_user, set_subscription, get_user_role, is_authorized
import sqlite3
from datetime import datetime

DB_FILE = "bot_data.db"

def list_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, number, full_name, role, subscription_active FROM users")
    users = cursor.fetchall()
    print("\n📋 Список пользователей:")
    for u in users:
        status = "✅ Подписка" if u[4] else "❌ Без подписки"
        print(f"ID: {u[0]} | №: {u[1]} | Имя: {u[2]} | Роль: {u[3]} | {status}")
    conn.close()

def delete_user(telegram_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()
    print(f"🗑 Пользователь {telegram_id} удалён.")

def main():
    while True:
        print("\n1. ➕ Добавить пользователя")
        print("2. 💎 Активировать подписку")
        print("3. 🚫 Деактивировать подписку")
        print("4. 📋 Показать пользователей")
        print("5. ❌ Удалить пользователя")
        print("0. 🔚 Выход")

        choice = input("\nВыбор: ")

        if choice == "1":
            user_id = input("Telegram ID: ")
            number = input("Табельный номер: ")
            full_name = input("ФИО: ")
            add_user(user_id, number, full_name)
            print("✅ Добавлен.")
        elif choice == "2":
            user_id = input("Telegram ID: ")
            set_subscription(user_id, active=True)
            print("✅ Подписка активирована.")
        elif choice == "3":
            user_id = input("Telegram ID: ")
            set_subscription(user_id, active=False)
            print("🚫 Подписка отключена.")
        elif choice == "4":
            list_users()
        elif choice == "5":
            user_id = input("Telegram ID: ")
            delete_user(user_id)
        elif choice == "0":
            break
        else:
            print("❌ Неверный выбор!")

if __name__ == "__main__":
    main()
