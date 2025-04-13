import sqlite3
from datetime import datetime

# Создаем подключение
conn = sqlite3.connect("bot_data.db")
cursor = conn.cursor()

# Создаем виртуальную таблицу FTS5
cursor.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
    title,
    description,
    revision,
    updated_at,
    path
)
""")

# Стартовые документы
documents = [
    (
        "Руководство по двигателю CFM56-7B",
        "Техническое руководство по эксплуатации и обслуживанию двигателя CFM56-7B.",
        "2.1",
        "2024-01-15",
        "documents/cfm56-7b.pdf"
    ),
    (
        "Руководство по двигателю PW1100G",
        "Документация по обслуживанию двигателя PW1100G для Airbus A320neo.",
        "1.3",
        "2024-02-01",
        "documents/pw1100g.pdf"
    ),
    (
        "Инструкция по устранению ошибки P1234",
        "Пошаговая инструкция по устранению ошибки P1234 в системе управления топливом.",
        "1.0",
        "2024-01-10",
        "documents/error_p1234.pdf"
    ),
]

# Вставка в таблицу
cursor.executemany("""
INSERT INTO documents (title, description, revision, updated_at, path)
VALUES (?, ?, ?, ?, ?)
""", documents)

conn.commit()
conn.close()

print("✅ База данных и стартовые документы успешно созданы.")

