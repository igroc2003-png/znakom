import sqlite3
from datetime import datetime

DB_PATH = "profiles.db"
GEO_DB = "geo.db"

# ================== PROFILES ==================

def create_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            gender TEXT,
            birthdate TEXT,
            age INTEGER,
            zodiac TEXT,
            city TEXT,
            about TEXT,
            photo_url TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_profile(user_id, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO profiles
        (user_id, name, gender, birthdate, age, zodiac, city, about, photo_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        data.get("name"),
        data.get("gender"),
        data.get("birthdate"),
        data.get("age"),
        data.get("zodiac"),
        data.get("city"),
        data.get("about"),
        data.get("photo_url")
    ))
    conn.commit()
    conn.close()


def get_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, gender, birthdate, age, zodiac, city, about, photo_url
        FROM profiles WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def delete_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# ================== ZODIAC ==================

def get_zodiac(day, month):
    if (month == 1 and day >= 20) or (month == 2 and day <= 18): return "♒ Водолей"
    if (month == 2 and day >= 19) or (month == 3 and day <= 20): return "♓ Рыбы"
    if (month == 3 and day >= 21) or (month == 4 and day <= 19): return "♈ Овен"
    if (month == 4 and day >= 20) or (month == 5 and day <= 20): return "♉ Телец"
    if (month == 5 and day >= 21) or (month == 6 and day <= 20): return "♊ Близнецы"
    if (month == 6 and day >= 21) or (month == 7 and day <= 22): return "♋ Рак"
    if (month == 7 and day >= 23) or (month == 8 and day <= 22): return "♌ Лев"
    if (month == 8 and day >= 23) or (month == 9 and day <= 22): return "♍ Дева"
    if (month == 9 and day >= 23) or (month == 10 and day <= 22): return "♎ Весы"
    if (month == 10 and day >= 23) or (month == 11 and day <= 21): return "♏ Скорпион"
    if (month == 11 and day >= 22) or (month == 12 and day <= 21): return "♐ Стрелец"
    return "♑ Козерог"


# ================== GEO SEARCH ==================

def normalize_city(text: str):
    text = text.strip()
    if not text:
        return ""
    return text[0].upper() + text[1:].lower()


def find_cities(prefix: str, limit=10):
    """
    Поиск С НАЧАЛА СЛОВА
    Работает корректно с кириллицей
    """
    if not prefix or len(prefix) < 2:
        return []

    prefix = normalize_city(prefix)

    conn = sqlite3.connect(GEO_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name
        FROM geo
        WHERE name LIKE ?
        ORDER BY important DESC, name ASC
        LIMIT ?
    """, (prefix + "%", limit))

    rows = [row[0] for row in cursor.fetchall()]
    conn.close()

    return rows
