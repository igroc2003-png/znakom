import sqlite3
import logging
import threading
import time
import asyncio
import redis.asyncio as redis
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from maxgram import Bot
from maxgram.keyboards import InlineKeyboard
from config import TOKEN, ADMIN_ID, SUPPORT_URL, IM_ESHOP_ID, IM_SECRET_KEY, IM_TEST, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
from yookassa import Configuration, Payment
import hashlib
import urllib.parse
import sys
import subprocess
import random
from config import BOT_USERNAME
#from payment import create_payment_link

# ================== ЛОГИ ==================

# Настройки логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - BOT - %(levelname)s - %(message)s")
log = logging.getLogger("BOT")


# ================== ИНИЦИАЛИЗАЦИЯ БОТА ==================
bot = Bot(TOKEN)

# ================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==================
GEO_DB = "geo.db"
DB_FILE = "profiles.db"        # Используем существующую таблицу профилей
users = {}                     # Временные данные при заполнении анкеты
user_states = {}               # Временные данные при заполнении таймера
queue = []                     # Очередь для игры в рулетку
active_chats = {}              # Активные чаты рулетки: user_id -> partner_id
contexts = {}                  # Контексты пользователей для рулетки: user_id -> ctx
chat_started_at = {}           # 👈 ВАЖНО (у тебя из-за этого была ошибка)
buh_process = None             # глобальная переменная для процесса buh.py
# Настройка YooKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY
# ======= Тарифы =======
TARIFFS = {
    "vip_30": {"days": 30, "price": 300, "name": "VIP 30 дней"},
    "vip_180": {"days": 180, "price": 1500, "name": "VIP 6 месяцев"},
    "vip_365": {"days": 365, "price": 2500, "name": "VIP 12 месяцев"},
}
# ================= REDIS =================
redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)
QUEUE_KEY = "roulette_queue"
async def start_chat(user1, user2):
    active_chats[user1] = user2
    active_chats[user2] = user1
    print(f"[CHAT STARTED] {user1} ↔ {user2}")
    
ZODIAC_SIGNS = {
    "Овен": "♈",
    "Телец": "♉",
    "Близнецы": "♊",
    "Рак": "♋",
    "Лев": "♌",
    "Дева": "♍",
    "Весы": "♎",
    "Скорпион": "♏",
    "Стрелец": "♐",
    "Козерог": "♑",
    "Водолей": "♒",
    "Рыбы": "♓",
}

def poll_payments_api_YOOKASSA():
    """
    Поток проверки платежей через YooKassa API.
    Каждые 30 секунд проверяет платежи со статусом 'pending'.
    Если платёж успешен, активирует VIP и отправляет главное меню.
    """
    while True:
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # Берём все pending платежи
            cursor.execute(
                "SELECT id, chat_id, payment_id, days FROM payments WHERE status='pending'"
            )
            payments = cursor.fetchall()

            for db_id, chat_id, payment_id, days in payments:
                try:
                    payment_info = Payment.get(payment_id)
                    status = payment_info.status  # "pending", "succeeded", "canceled"
                except Exception as e:
                    logging.error(f"YooKassa API error for {payment_id}: {e}")
                    continue

                if status != "succeeded":
                    continue  # Платёж ещё не выполнен

                # ✅ Обновляем статус платежа
                cursor.execute("UPDATE payments SET status='done' WHERE id=?", (db_id,))
                conn.commit()

                # ✅ Активируем VIP
                profile = get_profile(chat_id)
                if profile:
                    activate_vip_for_profile(profile, days)

                    cursor.execute(
                        "UPDATE profiles SET vip_until=? WHERE user_id=?",
                        (profile["vip_until"], profile["user_id"])
                    )
                    conn.commit()

                    # ✅ Уведомляем пользователя через API и отправляем главное меню
                    try:
                        text, keyboard = main_menu(profile, chat_id)
                        bot.api.send_message(
                            chat_id,
                            f"🎉 VIP активирован на {days} дней!\n\nСпасибо за поддержку ❤️\n\n{text}",
                            keyboard=keyboard
                        )
                    except Exception as e:
                        logging.error(f"poll_payments_api_YOOKASSA error: {e}")

        finally:
            if conn:
                conn.close()

        time.sleep(30)  # проверка каждые 30 секунд

# ================== Запуск матчмейкера ==================
async def start_matchmaker():
    asyncio.create_task(matchmaker())



# ================== КЛАВИАТУРЫ ==================
# Главное меню
def main_menu(profile=None, chat_id=None):
# Реальные числа из базы
    stats = get_stats()
    girls = 412
    boys = 230

# Суммарные числа (реальные + из базы)
    girls_total = girls + stats.get('users_f', 0)
    boys_total = boys + stats.get('users_m', 0)

# Онлайн = примерно половина суммарных пользователей + разброс
    online_total = (girls_total + boys_total) // 2 + random.randint(-15, 15)

# Ограничиваем, чтобы не выйти за реальные пределы
    online_total = max(1, min(online_total, girls_total + boys_total))

# Заголовок
    header_text = (
        f"🔥 Онлайн прямо сейчас: {online_total} человек\n"
        f"👩 Девушек всего: {girls_total}\n"
        f"👨 Парней всего: {boys_total}"
    )


    emoji = "👤"
    if profile:
        if profile.get("gender") == "М":
            emoji = "👨"
        elif profile.get("gender") == "Ж":
            emoji = "👩"

    buttons = [
        [{"text": "🎲 Начать общение", "callback": "ruletka"}],
        [{"text": "💎 VIP без ограничений", "callback": "vip"}],
        [{"text": f"{emoji} Моя анкета", "callback": "open_profile"}],
        [{"text": "🎯 Фильтры (VIP)", "callback": "open_filters"}],
        [{"text": "📩 Пригласить друзей 🎁", "callback": "invite"}],
        [{"text": "🆘 Поддержка", "url": SUPPORT_URL}],
    ]

    if chat_id and str(chat_id) == str(ADMIN_ID):
        buttons.append([{"text": "⚙ Админ панель", "callback": "admin_panel"}])

    keyboard = InlineKeyboard(*buttons)
    return header_text, keyboard   
    

# ================== Сохранение профиля ==================
save_menu = InlineKeyboard(
    [
        {"text": "Сохранить анкету", "callback": "save"},
        {"text": "Главное меню", "callback": "main_menu"}
    ]
)





def start_bot():
    """Запуск бота с автопереподключением при ошибках сети"""
    log.info("🚀 Bot started")
    while True:
        try:
            bot.polling(timeout=60)  # long polling
        except Exception as e:
            log.error(f"Ошибка long polling: {e}")
            log.info("Попытка переподключения через 5 секунд...")
            time.sleep(5)


# Клавиатура для оплаты
def pay_keyboard(pay_url):
    return InlineKeyboard(
        [{"text": "🔗 Перейти к оплате", "url": pay_url}],
        [{"text": "⬅️ Назад", "callback": "vip"}]
    )

# Клавиатура VIP
vip_keyboard = InlineKeyboard(
    [{"text": "💳 VIP 30 дней — 300 ₽", "callback": "vip_30"}],
    [{"text": "💳 VIP 6 месяцев — 1500 ₽", "callback": "vip_180"}],
    [{"text": "💳 VIP 12 месяцев — 2500 ₽", "callback": "vip_365"}],
    [{"text": "⬅️ Назад", "callback": "back"}]
	)

# Клавиатура VIP продление
vip_tarif_keyboard = InlineKeyboard(
    [{"text": "💳 VIP 30 дней — 300 ₽", "callback": "vip_30"}],
    [{"text": "💳 VIP 6 месяцев — 1500 ₽", "callback": "vip_180"}],
    [{"text": "💳 VIP 12 месяцев — 2500 ₽", "callback": "vip_365"}],
    [{"text": "⬅️ Назад", "callback": "back"}]
	)



# Клавиатура оферты VIP
vip_offer_keyboard = InlineKeyboard(
    [{"text": "✅ Согласен", "callback": "offer_accept"}],
    [{"text": "❌ Не согласен", "callback": "offer_decline"}]
)

# Клавиатура VIP
VIP_TEXT = (
    "Подключая подписку VIP чата-рулетки знакомств, вы соглашаетесь с условиями оферты.\n\n"
    "📄 Исполнитель услуг:\n"
    "Индивидуальный предприниматель\nМерзляков Алексей Владимирович\n"
    "ИНН: 420105283818\n"
    "ОГРНИП: 324420500025722\n\n"
    "💳 Оплата производится в форме предоплаты.\n"
    "🔁 Возврат средств не производится, за исключением случаев невозможности оказания услуги по техническим причинам.\n\n"
    "📦 Тарифы VIP-подписки:\n"
    "• 30 дней — 300 ₽\n"
    "• 6 месяцев — 1500 ₽\n"
    "• 12 месяцев — 2500 ₽"
)

vip_start_keyboard = InlineKeyboard(
    [{"text": "📄 Условия оферты", "callback": "show_offer"}],
    [{"text": "💎 Оформить VIP", "callback": "vip_tariv"}],
    [{"text": "⬅️ Назад", "callback": "back"}]
)   

OFFER_TEXT = """
📄 *ПУБЛИЧНАЯ ОФЕРТА*

Настоящая публичная оферта (далее — Оферта) устанавливает условия предоставления услуг подписки
на чат-рулетку знакомств (далее — Услуги) индивидуальным предпринимателем
(далее — Исполнитель). Оферта является предложением заключить договор на условиях,
изложенных ниже.

━━━━━━━━━━━━━━━━━━
*1. Предмет договора*

1.1. Исполнитель обязуется предоставить Пользователю доступ к Услугам подписки
на чат-рулетку знакомств, а Пользователь обязуется оплатить подписку
на условиях, изложенных в настоящей Оферте.

1.2. Услуги включают в себя:
• Общение в чате-рулетке без ограничений по времени  
• Доступ к дополнительным функциям и привилегиям

━━━━━━━━━━━━━━━━━━
*2. Стоимость и порядок оплаты*

2.1. Стоимость подписки:
• 30 дней — 300 ₽  
• 6 месяцев — 1500 ₽  
• 12 месяцев — 2500 ₽  

2.2. Оплата производится в форме предоплаты.
Возврат средств не осуществляется, за исключением случаев,
предусмотренных законодательством РФ.

━━━━━━━━━━━━━━━━━━
*3. Условия использования*

3.1. Пользователь обязуется соблюдать нормы этики и морали,
не распространять спам и не нарушать права других пользователей.

━━━━━━━━━━━━━━━━━━
*4. Ограничения без подписки*

4.1. Пользователи без подписки могут общаться в чате не более 3 минут,
после чего диалог автоматически завершается.

━━━━━━━━━━━━━━━━━━
*5. Конфиденциальность*

5.1. Исполнитель обеспечивает защиту персональных данных
в соответствии с законодательством РФ.

━━━━━━━━━━━━━━━━━━
*6. Заключительные положения*

6.1. Оферта вступает в силу с момента её акцепта Пользователем.

━━━━━━━━━━━━━━━━━━
📄 *Исполнитель услуг:*
ИП Мерзляков Алексей Владимирович  
ИНН: 420105283818  
ОГРНИП: 324420500025722
"""




 

# Клавиатура проверки возраста
age_keyboard = InlineKeyboard([
    {"text": "✅ Да, мне есть 18", "callback": "age_yes"},
    {"text": "❌ Нет", "callback": "age_no"},
])

# Выбор пола
gender_keyboard = InlineKeyboard([
    {"text": "👨 Мужской", "callback": "gender_m"},
    {"text": "👩 Женский", "callback": "gender_f"},
])









def get_edit_keyboard(is_saved=False):
    """
    Возвращает клавиатуру редактирования анкеты.
    is_saved=False -> редактируем новую анкету (создание)
    is_saved=True -> редактируем существующую анкету (профиль)
    """
    last_button = {
        "text": "👍 Готово 2" if is_saved else "👍 Готово 1",
        "callback": "edit_save_profile" if is_saved else "edit_done_create"
    }

    print(f"[DEBUG] Создаётся клавиатура редактирования, is_saved={is_saved}")
    print(f"[DEBUG] Кнопка 'Готово': text='{last_button['text']}', callback='{last_button['callback']}'")

    return InlineKeyboard(
        [{"text": "📝 Имя", "callback": "edit_name_profile" if is_saved else "edit_name_save"},
         {"text": "⚧ Пол", "callback": "edit_gender_profile" if is_saved else "edit_gender_save"}],
        [{"text": "🎂 Дата рождения", "callback": "edit_birthdate_profile" if is_saved else "edit_birthdate_save"},
         {"text": "🏙 Город", "callback": "edit_city_profile" if is_saved else "edit_city_save"}],
        [{"text": "✍️ О себе", "callback": "edit_about_profile" if is_saved else "edit_about_save"},
         {"text": "📸 Фото", "callback": "edit_photo_profile" if is_saved else "edit_photo_save"}],
        [last_button]
    )


























# Меню после заполнения анкеты
save_menu = InlineKeyboard([
    {"text": "💾 Сохранить ✅", "callback": "save"},
    {"text": "✏️ Редактировать", "callback": "edit_profile_after_creation"},
    {"text": "🗑 Удалить", "callback": "delete"}
])

# Кнопки просмотра анкеты
profile_menu = InlineKeyboard([
    {"text": "✏️ Редактировать", "callback": "edit_profile"},
    {"text": "🗑 Удалить", "callback": "delete_profile"},
    {"text": "⬅️ Назад", "callback": "back_to_menu"}
])

# Подтверждение удаления после заполнения
delete_save_menu = InlineKeyboard([
    {"text": "✅ Да, удалить", "callback": "menu_delete"},
    {"text": "❌ Нет", "callback": "cancel_menu_delete"}
])

# Подтверждение удаления из анкеты
delete_confirm_keyboard = InlineKeyboard([
    {"text": "✅ Да, удалить", "callback": "confirm_delete"},
    {"text": "❌ Нет", "callback": "cancel_delete"}
])

# Восстановление анкеты
restore_keyboard = InlineKeyboard([
    {"text": "♻️ Восстановить", "callback": "restore_profile"},
    {"text": "❌ Нет", "callback": "cancel_restore"}
])


# Клавиатура VIP
def vip_menu():
    return InlineKeyboard(
        [{"text": "💎 Оформить VIP", "callback": "vip"}],
        [{"text": "⬅️ В меню", "callback": "back"}]
    )




# Клавиатура рулетки
ruletka_keyboard = InlineKeyboard(
    [{"text": "▶ Найти собеседника", "callback": "roulette_in"}],
    [{"text": "⏹ Выйти из чата", "callback": "roulette_out"}]
)

# ================== БАЗА ДАННЫХ ==================
# ------------------ Создание базы и профилей ------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # ================= ПРОФИЛИ =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            gender TEXT,
            birthdate TEXT,
            age INTEGER,
            zodiac TEXT,
            city TEXT,
            region TEXT,
            about TEXT,
            photo_url TEXT,
            is_vip INTEGER DEFAULT 0,
            vip_until TEXT DEFAULT NULL,
            deleted_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            filters_gender TEXT DEFAULT 'Любой',
            filters_age_min INTEGER DEFAULT 18,
            filters_age_max INTEGER DEFAULT 35,
            filters_city TEXT DEFAULT 'Любой',
            filters_region TEXT DEFAULT 'Любой',
            is_subscribed INTEGER DEFAULT 0,
            subscription_expire TEXT DEFAULT NULL,
            invited_by TEXT DEFAULT NULL,
            invites INTEGER DEFAULT 0
        );
    """)

    # ===== Добавляем недостающие колонки =====
    columns_to_add = {
        "vip_order_id": "TEXT DEFAULT NULL",
        "vip_price": "REAL DEFAULT NULL",
        "last_activity": "INTEGER DEFAULT NULL"
    }

    cursor.execute("PRAGMA table_info(profiles);")
    existing_columns = [col[1] for col in cursor.fetchall()]

    # Добавляем недостающие колонки
    for column, definition in columns_to_add.items():
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE profiles ADD COLUMN {column} {definition};")
            print(f"Добавлена колонка: {column}")

    # ================= ACTIVE CHATS =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_chats (
            user1 TEXT,
            user2 TEXT,
            started_at INTEGER DEFAULT (strftime('%s','now'))
        );
    """)

    # ================= РУЛЕТКА =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roulette_queue (
            user_id TEXT PRIMARY KEY,
            joined_at INTEGER
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roulette_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            user_id TEXT,
            event TEXT,
            partner_id TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roulette_filters (
            user_id TEXT PRIMARY KEY,
            gender TEXT DEFAULT NULL,
            min_age INTEGER DEFAULT NULL,
            max_age INTEGER DEFAULT NULL,
            city TEXT DEFAULT NULL
        );
    """)

    # ================= ИСТОРИЯ ПОИСКА =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            searched_at INTEGER DEFAULT (strftime('%s','now'))
        );
    """)

    # ================= ИСТОРИЯ МАТЧЕЙ =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id TEXT,
            user2_id TEXT,
            matched_at INTEGER DEFAULT (strftime('%s','now'))
        );
    """)

    # ================= ТАЙМЕР =================
    # Создаём таблицу если её нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # Добавляем таймер по умолчанию 180 секунд (3 минуты)
    cursor.execute("""
        INSERT OR IGNORE INTO bot_settings (key, value)
        VALUES ('chat_timer', '180');
    """)

    # ================= РЕФЕРАЛЫ =================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            inviter_id TEXT,
            invited_id TEXT UNIQUE
        )
    """)

    # ================= ПРОВЕРКА НА НЕДОСТАЮЩИЕ КОЛОНКИ =================
    cursor.execute("PRAGMA table_info(profiles)")
    columns = [col[1] for col in cursor.fetchall()]
    if "vip_until" not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN vip_until TEXT")
        cursor.execute("PRAGMA table_info(profiles);")
        columns = [col[1] for col in cursor.fetchall()]
        print("✅ Колонка vip_until добавлена")

    if "invites" not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN invites INTEGER DEFAULT 0")
        print("Добавлена колонка: invites")

    # Коммитим изменения
    conn.commit()
    conn.close()

    print("✅ Все таблицы и колонки созданы/проверены")

# ------------------ Работа с таймером ------------------
def get_referral_progress(user_id):
    invited_users = get_users_invited_by(user_id)
    unique_friends = {u['chat_id'] for u in invited_users}
    total = len(unique_friends)

    progress = total % 3  # сколько сейчас в текущем цикле (0,1,2)
    return total, progress
    
def get_invites(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT invites FROM profiles WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0


def add_invite(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET invites = invites + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# Функция для установки таймера
def set_chat_timer(seconds):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('chat_timer', ?)", (str(seconds),))
    conn.commit()
    conn.close()
    log.info(f"Таймер обновлён на {seconds} секунд")

# Функция для получения текущего значения таймера
def get_chat_timer():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key='chat_timer'")
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 300
    
def check_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key='chat_timer'")
    row = cursor.fetchone()
    conn.close()
   

# ------------------ Работа с профилями ------------------
def get_profile(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, name, gender, birthdate, age, city, about, photo_url,
               filters_gender, filters_age_min, filters_age_max, filters_city
        FROM profiles
        WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    (user_id, name, gender, birthdate, age, city, about, photo_url,
     filters_gender, filters_age_min, filters_age_max, filters_city) = row

    return {
        "user_id": user_id,
        "name": name,
        "gender": gender,
        "birthdate": birthdate,
        "age": age,
        "city": city,
        "about": about,
        "photo_url": photo_url,
        "filters_gender": filters_gender,
        "filters_age_min": filters_age_min,
        "filters_age_max": filters_age_max,
        "filters_city": filters_city
    }

def save_profile(user_id, new_data):
    # Получаем текущий профиль из БД
    profile = get_profile(user_id) or {}

    # Обновляем только те поля, что есть в new_data
    profile.update(new_data)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO profiles (
            user_id, name, gender, birthdate, age, zodiac, city, region, about, photo_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        user_id,
        profile.get("name"),
        profile.get("gender"),
        profile.get("birthdate"),
        profile.get("age"),
        profile.get("zodiac"),
        profile.get("city"),
        profile.get("region"),
        profile.get("about"),
        profile.get("photo_url")
    ))
    conn.commit()
    conn.close()

def update_last_activity(user_id):
    now = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET last_activity=? WHERE user_id=?", (now, user_id))
    conn.commit()
    conn.close()

def delete_profile(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def soft_delete_profile(user_id):
    delete_date = int(time.time()) + 30 * 24 * 60 * 60  # 30 дней
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET deleted_at=? WHERE user_id=?", (delete_date, user_id))
    conn.commit()
    conn.close()


# ------------------ VIP ------------------
def activate_vip(user_id, days=3650):
    vip_time = datetime.now() + timedelta(days=days)
    vip_until_str = vip_time.strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET is_vip=1, vip_until=? WHERE user_id=?", (vip_until_str, user_id))
    conn.commit()
    conn.close()

def remove_vip(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET is_vip=0, vip_until=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def is_vip(user):
    vip_until = user.get("vip_until")
    if not vip_until:
        return False
    try:
        vip_time = datetime.strptime(vip_until, "%Y-%m-%d %H:%M:%S")
        return datetime.now() < vip_time
    except:
        return False

def save_order(order_id, user_id, days, price):
    vip_until = datetime.now() + timedelta(days=days)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE profiles
        SET is_vip=1, vip_until=?, vip_order_id=?, vip_price=?
        WHERE user_id=?
    """, (vip_until.strftime("%Y-%m-%d %H:%M:%S"), order_id, price, user_id))
    conn.commit()
    conn.close()


# ------------------ Фильтры ------------------
def update_filter(user_id, field, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE profiles SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()
    log.info(f"🔧 filter {field}={value} saved for {user_id}")
    
def filter(user_id, field, value):
    user_id = str(user_id)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE profiles SET {field}=? WHERE user_id=?",
        (value, user_id)
    )
    conn.commit()
    conn.close()

    log.info(f"🔧 filter {field}={value} saved for {user_id}")
    
def get_filters(user_id):
    user_id = str(user_id)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filters_city, filters_region, filters_gender, filters_age_min, filters_age_max
        FROM profiles
        WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    city, region, gender, age_min, age_max = row

    return {
        "city": city or "Любой",
        "region": region or "Любой",
        "gender": gender or "Любой",
        "age_min": age_min if age_min is not None else 18,
        "age_max": age_max if age_max is not None else 35
    }


# ------------------ Очередь рулетки ------------------
def add_to_queue(user_id):
    now = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO roulette_queue (user_id, joined_at) VALUES (?, ?)", (user_id, now))
    conn.commit()
    conn.close()

def remove_from_queue(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM roulette_queue WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_queue():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM roulette_queue ORDER BY joined_at")
    queue = [row[0] for row in cursor.fetchall()]
    conn.close()
    return queue

def log_search(user_id):
    now = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO roulette_stats (timestamp, user_id, event, partner_id) VALUES (?, ?, ?, ?)",
                   (now, user_id, "search", None))
    conn.commit()
    conn.close()

def log_match(user_id, partner_id):
    now = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO roulette_stats (timestamp, user_id, event, partner_id) VALUES (?, ?, ?, ?)",
                   (now, user_id, "match", partner_id))
    cursor.execute("INSERT INTO roulette_stats (timestamp, user_id, event, partner_id) VALUES (?, ?, ?, ?)",
                   (now, partner_id, "match", user_id))
    conn.commit()
    conn.close()

def activate_vip(user_id, days):
    vip_time = datetime.now() + timedelta(days=days)
    vip_until_str = vip_time.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE profiles SET is_vip=1, vip_until=? WHERE user_id=?",
        (vip_until_str, user_id)
    )
    conn.commit()
    conn.close()


#==================ФИЛЬТРЫ==========================================
MIN_AGE_LIMIT = 18
MAX_AGE_LIMIT = 100

gender_filters = InlineKeyboard(
    [
        {"text": "👨 Мужчины", "callback": "gender_filter_m"},
        {"text": "👩 Женщины", "callback": "gender_filter_f"},
    ],
    [
        {"text": "🎭 Любой", "callback": "gender_filter_any"},
    ],
    [
        {"text": "⬅ Назад", "callback": "open_filters"}
    ]
)



def keyboard_filters(profile):
    min_age = profile.get("filters_age_min") or 18
    max_age = profile.get("filters_age_max") or 35
    gender = profile.get("filters_gender") or "Любой"
    city = profile.get("filters_city") or "Любой"
    


    return InlineKeyboard(
        [
            {"text": f"Пол: {gender}", "callback": "gender_filters"},
        ],
        [
            {"text": f"Возраст: {min_age}-{max_age}", "callback": "age_filters"},
        ],
        [
            {"text": f"Город: {city}", "callback": "city_filters"},
        ],
        [
            {"text": "Сбросить фильтры", "callback": "filters_reset"},
        ],
        [
            {"text": "Готово", "callback": "back"},
        ]
    )

def show_filters(ctx):
    profile = get_profile(ctx.chat_id)
    if not profile:
        ctx.reply("Фильтры не найдены")
        return

    # берём значения из базы, только если None — дефолт
    min_age = profile.get("filters_age_min")
    max_age = profile.get("filters_age_max")
    gender = profile.get("filters_gender")
    city = profile.get("filters_city")

    if min_age is None:
        min_age = 18
    if max_age is None:
        max_age = 35
    if gender is None:
        gender = "Любой"
    if city is None:
        city = "Любой"

    emoji = "👨" if gender == "М" else "👩" if gender == "Ж" else "🎭"

    text = (
        f"⚙️ Ваши фильтры:\n\n"
        f"Пол: {gender} {emoji}\n"
        f"Возраст: {min_age}–{max_age}\n"
        f"Город: {city}"
    )

    ctx.reply(text, keyboard=keyboard_filters(profile))

# Возраст
def age_keyboard_filters(min_age, max_age):
    return InlineKeyboard(
        [
            {"text": "⬅️ Мин -1", "callback": "age_min_minus"},
            {"text": f"{min_age}", "callback": "noop"},
            {"text": "Мин +1 ➡️", "callback": "age_min_plus"},
        ],
        [
            {"text": "⬅️ Макс -1", "callback": "age_max_minus"},
            {"text": f"{max_age}", "callback": "noop"},
            {"text": "Макс +1 ➡️", "callback": "age_max_plus"},
        ],
        [
            {"text": "✅ Готово", "callback": "done_filters"}
        ]
    )











#=========================ПРИГЛАСИТЕЛЬНЫЙ ОБРАБОТКА=============

def minutes_text(seconds):
    return str(int(seconds//60)) + " мин" if seconds >= 60 else str(seconds) + " сек"

# ====== Сообщение рефералки ======
def invite_message(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Всего приглашённых за всё время
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (user_id,))
    row = cursor.fetchone()
    total_invited = row[0] if row else 0

    # Текущее количество приглашений до следующего VIP
    cursor.execute("SELECT invites FROM profiles WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    invites = row[0] if row else 0

    total = 3
    vip_awarded = False

    # Выдача VIP при достижении 3 приглашений
    if invites >= total:
        vip_until = datetime.now() + timedelta(days=1)
        cursor.execute("""
            UPDATE profiles
            SET vip_until = ?, invites = invites - ?
            WHERE user_id = ?
        """, (vip_until.strftime("%Y-%m-%d %H:%M:%S"), total, user_id))
        conn.commit()
        invites -= total
        vip_awarded = True

    conn.close()

    # Прогресс-бар
    filled = min(invites, total)
    progress = "█" * filled + "░" * (total - filled)
    remaining = max(0, total - invites)

    def plural(n, one, few, many):
        if n % 10 == 1 and n % 100 != 11:
            return one
        elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
            return few
        else:
            return many

    # Заголовок
    if vip_awarded:
        header = (
            "🎉🔥 Ты пригласил 3 друзей!\n\n"
            "💎 VIP активирован на 24 часа!\n\n"
            f"👥 Всего приглашено: {total}\n"
            "🚀 Продолжай приглашать и получай ещё VIP!"
        )
    else:
        header = (
            f"👥 Ты уже пригласил: {total_invited} {plural(total_invited,'друга','друга','друзей')}\n\n"
            f"🧑‍🤝‍🧑 Прогресс: {invites} / {total} {progress}\n"
            f"🔥 Осталось {remaining} {plural(remaining,'друг','друга','друзей')} до VIP!"
        )

    invite_link = f"https://max.ru/{BOT_USERNAME}?start={user_id}"

    text = (
        f"🎁 Получай VIP бесплатно!\n\n"
        f"{header}\n\n"
        f"📩 Твоя персональная ссылка:\n{invite_link}\n\n"
        "Отправь её друзьям и получай бонусы 💬🔥\n\n"
        f"💎 За каждых {total} друзей — 1 день VIP"
    )

    keyboard = InlineKeyboard([
        {"text": "🏠 Главное меню", "callback": "main_menu"}
    ])

    return text, keyboard



#=====================================================================================

def create_profile(user_id, invited_by=None):
    """Создаёт новый профиль пользователя в базе, если его нет"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO profiles (
            user_id, name, gender, birthdate, age, zodiac,
            city, region, about, photo_url, is_vip,
            invites, vip_until, invited_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, "", "", "", 0, "",
        "", "", "", "", 0,
        0, None, invited_by
    ))

    conn.commit()
    conn.close()

def create_profile_if_not_exists(user_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # проверяем, есть ли профиль
    cur.execute("SELECT 1 FROM profiles WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        # если нет — создаём
        cur.execute("""
            INSERT INTO profiles (user_id, invites, vip_until)
            VALUES (?, 0, NULL)
        """, (user_id,))
        print(f"PROFILE CREATED: {user_id}")
        conn.commit()
    else:
        print(f"PROFILE EXISTS: {user_id}")

    conn.close()

def process_referral(inviter_id, invited_id):
    """
    Обрабатывает приглашение нового пользователя
    """

    if inviter_id == invited_id:
        return  # нельзя пригласить самого себя

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Проверяем, не был ли уже добавлен этот invited_id
        cursor.execute(
            "SELECT 1 FROM referrals WHERE invited_id=?",
            (invited_id,)
        )
        if cursor.fetchone():
            return  # уже учитывался

        # Добавляем запись
        cursor.execute(
            "INSERT INTO referrals (inviter_id, invited_id) VALUES (?, ?)",
            (inviter_id, invited_id)
        )

        # Увеличиваем invites
        cursor.execute(
            "UPDATE profiles SET invites = invites + 1 WHERE user_id=?",
            (inviter_id,)
        )

        conn.commit()

    finally:
        conn.close()

def register_new_user(new_user_id, inviter_id=None):
    """
    Создаёт профиль нового пользователя и, если есть пригласивший, добавляет запись в referrals
    и увеличивает счётчик invites.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Создаём профиль, если ещё нет
        cursor.execute(
            "INSERT OR IGNORE INTO profiles (user_id, invites) VALUES (?, 0)",
            (new_user_id,)
        )
        conn.commit()

        if inviter_id and inviter_id != new_user_id:
            # Добавляем запись в referrals (уникально)
            cursor.execute(
                "INSERT OR IGNORE INTO referrals (inviter_id, invited_id) VALUES (?, ?)",
                (inviter_id, new_user_id)
            )
            conn.commit()

            # Увеличиваем invites и проверяем на VIP
            add_invite(inviter_id)
    finally:
        conn.close()


def add_invite(user_id):
    """
    Увеличивает счётчик приглашений и выдаёт VIP на 1 день за каждые 3 приглашения.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Увеличиваем счётчик
        cursor.execute("UPDATE profiles SET invites = invites + 1 WHERE user_id=?", (user_id,))
        conn.commit()

        # Получаем новое значение
        cursor.execute("SELECT invites FROM profiles WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        invites = row[0] if row else 0

        if invites >= 3:
            # Выдаём VIP на 1 день
            vip_until = datetime.now() + timedelta(days=1)
            cursor.execute("""
                UPDATE profiles
                SET vip_until = ?, invites = invites - 3
                WHERE user_id=?
            """, (vip_until.strftime("%Y-%m-%d %H:%M:%S"), user_id))
            conn.commit()
    finally:
        conn.close()
        
# ================== УНИВЕРСАЛЬНАЯ ОБРАБОТКА ПОЛ ==================
    # ------------------ ОБРАБОТЧИК ВЫБОРА ПОЛА ------------------
def process_gender_selection(ctx, chat_id, payload):
    u = users[chat_id]

    if u.get("step") != "gender_select":
        return True

    # Сохраняем выбранный пол
    u["gender"] = "М" if payload == "gender_m" else "Ж"

    if u.get("mode") == "edit":
        save_profile(chat_id, u)
        u["step"] = None
        u["is_editing"] = False

        # Показываем клавиатуру редактирования с правильным "Готово"
        ctx.reply(
            "Пол обновлён ✅",
            keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
        )
        return True

    # если создание анкеты
    u["step"] = "birth_day"
    ctx.reply("Введите день рождения (1-31):")
    return True
        
# ================== УНИВЕРСАЛЬНАЯ ОБРАБОТКА ДАТЫ РОЖДЕНИЯ ==================
def handle_birthdate(ctx, u, chat_id, step, text, creation=True):
    """
    Универсальный блок для ввода даты рождения.
    - step: birth_day / birth_month / birth_year или edit_birth_day / edit_birth_month / edit_birth_year
    - creation=True -> создание анкеты (лимит 18+)
    - creation=False -> редактирование анкеты (лимит 14–100)
    """

    if step in ("birth_day", "edit_birth_day"):
        if not text.isdigit() or not 1 <= int(text) <= 31:
            ctx.reply("Введите число от 1 до 31")
            return
        u["birth_day"] = int(text)
        u["step"] = "birth_month" if step == "birth_day" else "edit_birth_month"
        ctx.reply("Введите месяц рождения (1-12):")
        return

    if step in ("birth_month", "edit_birth_month"):
        if not text.isdigit() or not 1 <= int(text) <= 12:
            ctx.reply("Введите число от 1 до 12")
            return
        u["birth_month"] = int(text)
        u["step"] = "birth_year" if step == "birth_month" else "edit_birth_year"
        ctx.reply("Введите год рождения:")
        return

    if step in ("birth_year", "edit_birth_year"):
        if not text.isdigit():
            ctx.reply("Введите год числом")
            return

        year = int(text)
        try:
            birthdate = datetime(year, u["birth_month"], u["birth_day"])
        except ValueError:
            ctx.reply("Некорректная дата")
            u["step"] = "birth_day" if step == "birth_year" else "edit_birth_day"
            return

        # Вычисляем возраст
        today = datetime.now()
        age = today.year - year - ((today.month, today.day) < (u["birth_month"], u["birth_day"]))

        # Проверка возраста
        if creation and age < 18:
            ctx.reply("Вам должно быть 18+ 🚫")
            u["step"] = None
            return

        if not creation and (age < 14 or age > 100):
            ctx.reply("Некорректная дата рождения")
            u["step"] = "edit_birth_day"
            return

        u["birthdate"] = birthdate.strftime("%d.%m.%Y")
        u["age"] = age
        u["zodiac"] = get_zodiac(u["birth_day"], u["birth_month"])

    # -------- РАЗДЕЛЯЕМ СОЗДАНИЕ И РЕДАКТИРОВАНИЕ --------

    if creation:
        u["step"] = "city_search"
        u["city_mode"] = "profile_create"

        save_profile(chat_id, {
            "birthdate": u["birthdate"],
            "age": u["age"],
            "zodiac": u["zodiac"]
        })

        ctx.reply("Введите первые буквы города:")
        return

    else:
        u["step"] = "edit"

        save_profile(chat_id, {
            "birthdate": u["birthdate"],
            "age": u["age"],
            "zodiac": u["zodiac"]
        })

        keyboard = get_edit_keyboard(is_saved=u.get("editing_existing", False))
        ctx.reply("Дата рождения сохранена ✅", keyboard=keyboard)
        return
# ================== УНИВЕРСАЛЬНЫЙ ВЫБОР ГОРОДА ==================
def send_city_selection(ctx, text, limit=5):
    """
    Безопасная функция поиска города и отправки клавиатуры выбора.
    Поиск нечувствителен к регистру, region может быть пустой.
    """
    chat_id = str(ctx.chat_id)
    text = text.strip()
    
    if len(text) < 2:
        ctx.reply("Введите минимум 2 символа")
        return

    # Для поиска нечувствительно к регистру
    search_text = f"{text[0].upper()}{text[1:].lower()}%"

    try:
        conn = sqlite3.connect(GEO_DB)
        cursor = conn.cursor()

        # Берём города, где name LIKE поисковому тексту
        cursor.execute(
            "SELECT name, region FROM geo WHERE name LIKE ? ORDER BY name LIMIT ?",
            (search_text, limit)
        )
        cities = cursor.fetchall()

        # Если Москва или Санкт-Петербург подходят под текст, добавим их вручную
        # чтобы гарантировать отображение
        special_cities = [("Москва", ""), ("Санкт-Петербург", "")]
        for sc in special_cities:
            if text.lower() in sc[0].lower() and sc not in cities:
                cities.insert(0, sc)

        conn.close()
    except Exception as e:
        ctx.reply(f"Ошибка базы данных: {e}")
        return

    if not cities:
        ctx.reply("Города не найдены, попробуйте ещё")
        return

    # Формируем кнопки безопасно
    kb_rows = []
    for name, region in cities:
        region_safe = region if region else "—"
        safe_callback = f"city_selected:{name.replace(' ', '_').replace(':', '_')}|{region_safe.replace(' ', '_')}"
        kb_rows.append([{"text": f"{name} ({region_safe})", "callback": safe_callback}])

    kb = InlineKeyboard(*kb_rows)
    ctx.reply("Выберите город:", keyboard=kb)


# ================== GEO ==================
def find_cities(prefix, limit=10):
    """Поиск городов по введённому префиксу"""
    try:
        conn = sqlite3.connect("geo.db")
        cursor = conn.cursor()
        prefix = prefix.capitalize()
        cursor.execute("SELECT name, region FROM geo WHERE name LIKE ? LIMIT ?", (prefix + "%", limit))
        cities = cursor.fetchall()
        conn.close()
        return cities
    except:
        return []

# ================== ПОКАЗ ПРОФИЛЯ ==================
def show_profile(ctx, profile, keyboard, zodiac_name=None, zodiac_sign=None):
    """
    Отображает анкету пользователя или партнёра с эмодзи пола и знаком зодиака.
    """
    if zodiac_name and zodiac_sign:
        zodiac_text = f"{zodiac_sign} {zodiac_name}"
    else:
        zodiac_text = profile.get("zodiac", "")
    # Эмодзи по полу
    emoji = "👤"
    if profile.get("gender") == "М":
        emoji = "👨"
    elif profile.get("gender") == "Ж":
        emoji = "👩"

    # Знак зодиака с эмодзи
    zodiac_name = profile.get("zodiac")
    zodiac_emoji = ZODIAC_SIGNS.get(zodiac_name, "") if zodiac_name else ""
    zodiac_display = f"{zodiac_emoji} {zodiac_name}" if zodiac_name else "Не указан"

    # VIP статус
    vip_status = "Да" if profile.get("is_vip") else "Нет"

    text = (
        f"{emoji} Анкета:\n\n"
        f"Имя: {profile.get('name')}\n"
        f"Пол: {profile.get('gender')}\n"
        f"🎂 Дата рождения: {profile.get('birthdate')}\n"
        f"🎈 Возраст: {profile.get('age')}\n"
        f"🪐 Знак зодиака: {zodiac_display}\n"
        f"🏙 Город: {profile.get('city')}\n"
        f"✍️ О себе: {profile.get('about')}\n"
        f"💎 VIP: {vip_status}\n"
        f"📸 Фото:\n{profile.get('photo_url')}"
    )

    ctx.reply(text, keyboard=keyboard)
        
# ================== УНИВЕРСАЛЬНАЯ АКТИВАЦИЯ VIP ==================
def activate_vip_for_profile(profile, days):
    now = datetime.now()
    vip_until_str = profile.get("vip_until")
    if vip_until_str:
        try:
            vip_until = datetime.strptime(vip_until_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            vip_until = now
        new_vip_until = vip_until + timedelta(days=days) if vip_until > now else now + timedelta(days=days)
    else:
        new_vip_until = now + timedelta(days=days)

    profile["vip_until"] = new_vip_until.strftime("%Y-%m-%d %H:%M:%S")
    profile["is_vip"] = True
    save_profile(profile)
    return new_vip_until

# ================== ОБРАБОТКА VIP КОМАНД АДМИНА ==================
def handle_vip_commands(ctx, text):
    chat_id = str(ctx.chat_id)
    if not text or chat_id != ADMIN_ID:
        return

    parts = text.strip().split()
    cmd = parts[0].lower()
    if cmd not in ("/givevip", "/removevip"):
        return

    try:
        user_id = int(parts[1])
    except (IndexError, ValueError):
        ctx.reply(f"Использование: {cmd} user_id [дни]" if cmd == "/givevip" else f"Использование: {cmd} user_id")
        return

    profile = get_profile(user_id)
    if not profile:
        ctx.reply(f"Профиль пользователя {user_id} не найден ❌")
        return

    if cmd == "/givevip":
        try:
            days = int(parts[2])
        except (IndexError, ValueError):
            ctx.reply("Использование: /givevip user_id дни")
            return
        new_vip_until = activate_vip_for_profile(profile, days)
        ctx.reply(f"VIP выдан пользователю {user_id} до {new_vip_until.strftime('%d.%m.%Y')} ✅")
    else:
        profile["vip_until"] = None
        profile["is_vip"] = False
        save_profile(profile)
        ctx.reply(f"VIP удалён у пользователя {user_id} ✅")
        
# ================== ЗОДИАК ==================
def get_zodiac(day, month):
    zodiac_dates = [
        (120, "Козерог"), (218, "Водолей"), (320, "Рыбы"), (420, "Овен"),
        (521, "Телец"), (621, "Близнецы"), (722, "Рак"), (823, "Лев"),
        (923, "Дева"), (1023, "Весы"), (1122, "Скорпион"), (1222, "Стрелец"), (1231, "Козерог")
    ]
    n = month * 100 + day
    for end, sign in zodiac_dates:
        if n <= end:
            return sign
    return "Козерог"


# ================== СОЗДАНИЕ АНКЕТЫ ===================
def process_profile_creation(ctx, u, text, attachments):
    chat_id = str(ctx.chat_id)
    step = u.get("step")

    # ------------------ Защита редактирования ------------------
    if u.get("is_editing"):
        return

    # ---------- Имя ----------
    if step == "name":
        if not text:
            ctx.reply("Введите имя")
            return

        u["name"] = text

        # ⚠ ВАЖНО — теперь шаг не gender, а gender_select
        u["step"] = "gender_select"

        ctx.reply("Выберите пол:", keyboard=gender_keyboard)
        return

    # ---------- День/Месяц/Год рождения ----------
    if step in ("birth_day", "birth_month", "birth_year"):
        handle_birthdate(ctx, u, chat_id, step, text, creation=True)
        return

    # ---------- Город ----------
    if step == "city_search":
        send_city_selection(ctx, text)
        return

    # ---------- О себе ----------
    if step == "about":
        if not text:
            ctx.reply("Напишите о себе")
            return
        u["about"] = text
        u["step"] = "photo"
        ctx.reply("Пришлите фото (картинка или ссылка):")
        return

    # ---------- Фото ----------
    if step == "photo":
        photo_url = None
        for att in attachments:
            if att.get("type") == "image":
                photo_url = att.get("payload", {}).get("url")
                break

        if not photo_url and text.startswith("http"):
            photo_url = text

        if not photo_url:
            ctx.reply("Фото не найдено, пришлите изображение")
            return

        u["photo_url"] = photo_url
        u["step"] = None
        save_profile(chat_id, u)

    # ---------- Отображение анкеты ----------
    zodiac_name = u.get("zodiac_name") or u.get("zodiac") or "Не указан"
    zodiac_sign = u.get("zodiac_sign") or ZODIAC_SIGNS.get(zodiac_name, "")

    show_profile(ctx, u, save_menu, zodiac_name=zodiac_name, zodiac_sign=zodiac_sign)
    
    
        
# ================== УНИВЕРСАЛЬНОЕ РЕДАКТИРОВАНИЕ ==================
# ================== УНИВЕРСАЛЬНОЕ РЕДАКТИРОВАНИЕ ==================
def handle_profile_edit(ctx, u, step, text, attachments):
    """
    Универсальный обработчик редактирования анкеты через клавиатуру.
    - step: текущий шаг редактирования
    - editing_existing = True -> редактируем существующую анкету
    """
    chat_id = str(ctx.chat_id)
    is_saved = u.get("editing_existing", False)

    # ------------------ Имя ------------------
    if step == "edit_name":
        if not text:
            print("[DEBUG] Имя не введено, запрашиваем снова")
            ctx.reply("Введите имя:")
            return True

        u["name"] = text.strip()
        if u.get("editing_existing", False):
            save_profile(chat_id, u)
        ctx.reply(
            "Имя обновлено ✅",
            keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
        )
        u["step"] = None
        u["is_editing"] = False  # Сбрасываем режим редактирования
        return True

    # ------------------ Пол ------------------
    # ------------------ ОБРАБОТЧИК ВЫБОРА ПОЛА ------------------
    if step == "gender_select":
        if text not in ("М", "Ж"):
            ctx.reply("Выберите пол кнопкой 👆")
            return True

        chat_id = str(ctx.chat_id)
        u["gender"] = text

        # Если редактирование — сохраняем и возвращаем на предыдущую клавиатуру
        if u.get("mode") == "edit":
            save_profile(chat_id, u)
            u["step"] = None
            u["is_editing"] = False

            # Определяем, какая клавиатура была до выбора пола
            print = u.get("return_keyboard")
            prev_payload = u.get("return_keyboard")
            if prev_payload in ("edit_gender_save", "edit_gender_profile"):
                # Показываем profile_menu или save_menu в зависимости от payload
                keyboard = save_menu if prev_payload == "edit_gender_save" else profile_menu
            else:
                # По умолчанию — клавиатура редактирования
                keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))

            ctx.reply("Пол обновлён ✅", keyboard=keyboard)
        return True




    # ------------------ Обработка даты рождения в handle_profile_edit ------------------
    if step in ("edit_birth_day", "edit_birth_month", "edit_birth_year"):
        print(f"[DEBUG] Шаг редактирования даты рождения: {step}")
        print(f"[DEBUG] Ввод пользователя: {text}")

        handle_birthdate(ctx, u, chat_id, step, text, creation=not u.get("editing_existing", False))

        # Проверяем, завершено ли редактирование
        if step == "edit_birth_year" and u.get("birthdate"):
            print(f"[DEBUG] Дата рождения обновлена: {u['birthdate']}")
            ctx.reply(
                "Дата рождения обновлена ✅",
                keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
            )
            u["step"] = None

        return True

    # ------------------ Город ------------------
    # ------------------ ТЕКСТОВЫЙ ВВОД ГОРОДА ------------------
    if step in ("city_search", "edit_city_search_"):
        if not text or len(text.strip()) < 2:
            ctx.reply("Введите минимум 2 буквы города")
            return True

        # просто вызываем функцию поиска и формирования клавиатуры
        send_city_selection(ctx, text)
        return True

    # ------------------ НАЖАТИЕ КНОПКИ ГОРОДА ------------------
    elif ctx.payload and ctx.payload.startswith("city_selected:"):
        chat_id = str(ctx.chat_id)
        users.setdefault(chat_id, {"step": None})
        u = users[chat_id]

        data = ctx.payload.replace("city_selected:", "")
        city, region = data.split("|")
        city = city.replace("_", " ")
        region = region.replace("_", " ") if region != "—" else ""

        u["city"] = city
        u["region"] = region

        # Сохраняем в базе
        save_profile(chat_id, u)

        # Показываем клавиатуру редактирования
        ctx.reply(
            f"Город обновлён: {city} ✅",
            keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
        )

        u["step"] = None
        return True








    # ------------------ О себе ------------------
    if step == "edit_about":
        print(f"[DEBUG] Шаг редактирования 'О себе': {step}")
        print(f"[DEBUG] Ввод пользователя: {text}")

        if not text:
            print("[DEBUG] Текст не введён, запрашиваем снова")
            ctx.reply("Напишите немного о себе:")
            return True

        u["about"] = text.strip()
        print(f"[DEBUG] Поле 'О себе' обновлено во временном профиле: {u['about']}")

        if u.get("editing_existing", False):
            save_profile(chat_id, u)
            print(f"[DEBUG] Поле 'О себе' сохранено в базе для chat_id={chat_id}")

        ctx.reply(
            "О себе обновлено ✅",
            keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
        )

        u["step"] = None
        return True

    # ------------------ Ввод фото ------------------
    if step == "edit_photo":
        print(f"[DEBUG] Шаг редактирования фото: {step}")
        print(f"[DEBUG] Вложения пользователя: {attachments}")

        if not attachments:
            print("[DEBUG] Фото не отправлено, запрашиваем снова")
            ctx.reply("Отправьте фото:")
            return True

        # Сохраняем первую присланную фотку
        photo_url = attachments[0].get("payload", {}).get("url")
        if not photo_url:
            print("[DEBUG] Ссылка на фото отсутствует, запрашиваем снова")
            ctx.reply("Отправьте корректное фото:")
            return True

        u["photo_url"] = photo_url
        print(f"[DEBUG] Фото обновлено во временном профиле: {photo_url}")

        if u.get("editing_existing", False):
            save_profile(chat_id, u)
            print(f"[DEBUG] Фото сохранено в базе для chat_id={chat_id}")

        # Показываем клавиатуру редактирования для следующего шага анкеты
        ctx.reply(
            "Фото обновлено ✅",
            keyboard=get_edit_keyboard(is_saved=u.get("editing_existing", False))
        )
        print("[DEBUG] Клавиатура редактирования показана")

        u["step"] = None
        return True

    # ------------------ Кнопка Готово ------------------
    if step in ("edit_save_profile", "edit_done_create"):
        u["step"] = None

        if is_saved:
            profile = load_profile(chat_id)
            show_profile(ctx, profile, save_menu)
            ctx.reply(
                "Редактирование завершено ✅",
                keyboard=get_edit_keyboard(is_saved=True)
            )
        else:
            save_profile(chat_id, u)
            show_profile(ctx, u, save_menu)
            ctx.reply(
                "Анкета создана ✅",
                keyboard=get_edit_keyboard(is_saved=True)
            )
        return True

    return False














def vip_active(profile):
    """
    Проверяет, активен ли VIP.
    profile — словарь профиля с полем 'vip_until' как текст в формате 'YYYY-MM-DD HH:MM:SS'
    """
    if not profile:
        return False

    vip_until = profile.get("vip_until")
    if not vip_until:
        return False

    try:
        # Преобразуем строку в datetime
        vip_time = datetime.strptime(vip_until, "%Y-%m-%d %H:%M:%S")
        return datetime.now() < vip_time
    except Exception as e:
        
        return False

# ==================== Фильтры ====================
def get_filters(user_id):
    """Возвращает фильтры пользователя из базы (город, пол)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filters_city, filters_gender
        FROM profiles
        WHERE user_id=?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {}

    city, gender = row
    filters = {}
    if city:
        filters["city"] = city
    if gender:
        filters["gender"] = gender
    return filters

# ==================== VIP Проверка ====================
def is_vip(profile):
    return profile.get("is_vip", False)




# ================== ОБРАБОТКА ВВОДА ГОРОДА ==================
@bot.on("message_created")
def relay(ctx):
    user_id = str(ctx.chat_id)
    contexts[user_id] = ctx

    print("\n========== NEW MESSAGE ==========")
    print(f"[DEBUG] user_id: {user_id}")
    print(f"[DEBUG] payload: {ctx.payload}")

    text = ctx.message.get("text") or ctx.message.get("body", {}).get("text")
    print(f"[DEBUG] raw text: {text}")

    # 🔹 1. Сначала шаги анкеты
    step_handled = text_steps(ctx)
    print(f"[DEBUG] text_steps returned: {step_handled}")

    if step_handled:
        print("[DEBUG] Сообщение обработано шагами анкеты")
        return

    # 🔹 2. Если это callback — выходим
    if ctx.payload:
        print("[DEBUG] Это callback, выходим")
        return

    # 🔹 3. Если не в чате — выходим
    if user_id not in active_chats:
        print("[DEBUG] Пользователь не в активном чате")
        return

    partner_id = active_chats[user_id]

    if not text:
        print("[DEBUG] Текста нет")
        return

    print(f"[Relay] {user_id} -> {partner_id}: {text}")

    if partner_id in contexts:
        contexts[partner_id].reply(text)       
        
def text_steps(ctx):
    chat_id = str(ctx.chat_id)
    users.setdefault(chat_id, {"step": None})
    u = users[chat_id]
    step = u.get("step")

    print(f"[DEBUG text_steps] step: {step}")

    if not step:
        print("[DEBUG text_steps] step отсутствует")
        return False

    text = ctx.message.get("text") or ctx.message.get("body", {}).get("text", "")
    attachments = ctx.message.get("body", {}).get("attachments", [])

    print(f"[DEBUG text_steps] text: {text}")
    print(f"[DEBUG text_steps] is_editing: {u.get('is_editing')}")

    # ------------------ РЕДАКТИРОВАНИЕ ------------------
    if u.get("is_editing"):
        print("[DEBUG text_steps] Переходим в handle_profile_edit")
        result = handle_profile_edit(ctx, u, step, text, attachments)
        print(f"[DEBUG text_steps] handle_profile_edit вернул: {result}")
        return result

    # ------------------ СОЗДАНИЕ АНКЕТЫ ------------------
    print("[DEBUG text_steps] Переходим в process_profile_creation")
    process_profile_creation(ctx, u, text, attachments)

    print("[DEBUG text_steps] Проверяем VIP команды")
    handle_vip_commands(ctx, text)

    return True

# Единый обработчик кнопок оплаты
def handle_vip(ctx, chat_id):
    payload = ctx.payload

    if payload not in tariffs:
        ctx.reply("❌ Неизвестный тариф")
        return

    tariff = tariffs[payload]
    profile = get_profile(chat_id)

    # Проверка, активен ли VIP
    if profile.get("vip_until"):
        try:
            vip_until = datetime.strptime(profile["vip_until"], "%Y-%m-%d %H:%M:%S")
            if vip_until > datetime.now():
                ctx.reply("💎 VIP уже активен")
                return
        except ValueError:
            pass

    # Генерация ссылки на оплату через IntellectMoney (или другой метод)
    order_id = f"{chat_id}_{int(time.time())}"
    link = intellectmoney_link(
        order_id=order_id,
        amount=tariff["price"],
        client_email="email@address.com"
    )

    # Отправляем клавиатуру оплаты
    ctx.reply(
        f"{tariff['name']}\nСтоимость: {tariff['price']} ₽\nВыберите способ оплаты 👇",
        keyboard=InlineKeyboard(
            [{"text": "💳 Банковская карта (IntellectMoney)", "url": link}],
            [{"text": "🟣 ЮMoney", "url": link}],
            [{"text": "⚡ СБП", "url": link}],
            [{"text": "🟢 SberPay", "url": link}],
            [{"text": "❌ Отмена", "callback": "back"}]
        )
    )

# Обработчик подтверждения оплаты (пример)
def handle_payment_confirmation(chat_id, payload):
    if payload not in tariffs:
        return

    tariff = tariffs[payload]
    profile = get_profile(chat_id)
    new_vip_until = activate_vip_for_profile(profile, tariff["days"])
    
    # Ответ пользователю
    return f"💎 VIP активирован на {tariff['days']} дней!\nДействует до: {new_vip_until.strftime('%d.%m.%Y %H:%M')}"


@bot.on("message_created")

#Установка таймера в админке
def handle_timer_input(ctx):
    state = user_states.get(str(ctx.chat_id))
    if state != "waiting_timer":
        return  # пользователь не в режиме ввода таймера

    # безопасно получаем текст
    text = ctx.message.get("body", {}).get("text")
    if not text or not text.isdigit():
        ctx.reply("⛔ Пожалуйста, введите число секунд (10-3600).")
        return

    seconds = int(text)
    if seconds < 10 or seconds > 3600:
        ctx.reply("⛔ Таймер должен быть от 10 до 3600 секунд. Попробуйте ещё раз.")
        return

    # сохраняем в базу
    set_chat_timer(seconds)
    ctx.reply(f"✅ Таймер успешно обновлён: {seconds} секунд")

    # сбрасываем состояние
    user_states.pop(str(ctx.chat_id), None)







# ================== СТАРТ ==================

@bot.on("bot_started")
def start(ctx):
    chat_id = str(ctx.chat_id)
    payload = ctx.payload  # inviter_id если пришёл по ссылке
    print(f"BOT_STARTED: chat_id={chat_id}, payload={payload}")

    users.setdefault(chat_id, {"step": None})

    # проверяем, есть ли профиль
    profile = get_profile(chat_id)
    if profile:
        print(f"Профиль найден: {profile['user_id']}")
    else:
        print("Профиля нет, создаём новый")

        invited_by = None
        if payload and payload != chat_id:
            invited_by = payload
            print(f"Пользователь пришёл по реферальной ссылке от {invited_by}")

        # создаём профиль
        create_profile(chat_id, invited_by=invited_by)

        # записываем реферала
        if invited_by:
            process_referral(invited_by, chat_id)
            print(f"Записали в referrals: {invited_by} -> {chat_id}")

        # первый шаг анкеты
        ctx.reply("🔞 Вам есть 18 лет?", keyboard=age_keyboard)
        return

    # профиль помечен на удаление
    if profile.get("deleted_at"):
        ctx.reply("⚠️ Ваша анкета помечена на удаление. Восстановить?", keyboard=restore_keyboard)
        return

    # если профиль есть — главное меню
    text, keyboard = main_menu(get_profile(chat_id), chat_id)
    ctx.reply(text, keyboard=keyboard)
    
   


# Обработчик колбэков
# Обработчик колбэков
# Обработчик колбэков
# Обработчик колбэков
# Обработчик колбэков
@bot.on("message_callback")
def handle_callback(ctx):

   
    
    
    chat_id = str(ctx.chat_id)
    data = ctx.payload
    payload = ctx.payload
    update_last_activity(chat_id)
    users.setdefault(chat_id, {"step": None})
    u = users[chat_id]
    profile = get_profile(chat_id)
    
    
    
    
    
    
    
    

 
    
    # ======= Обработка тарифов =======
    if payload in TARIFFS:
        tariff = TARIFFS[payload]
        try:
            # Генерируем уникальный order_id
            order_id = f"{chat_id}_{int(time.time())}"
            
            # 👉 Генерация ссылки IntellectMoney
            intellectmoney_link_url = intellectmoney_link(
            order_id=order_id,
            amount=tariff["price"],
            client_email="test@email.ru"
        )


            # Создаём платеж в YooKassa
            payment = Payment.create({
                "amount": {
                    "value": str(tariff["price"]),
                    "currency": "RUB"
                },
                "confirmation": {
                   "type": "redirect",
                    "return_url": f"https://t.me/YourBotUsername?start=pay_{order_id}"
                },
                "capture": True,
                "description": f"Оплата {tariff['name']} для пользователя {chat_id}",
                "metadata": {
                    "chat_id": chat_id,
                    "order_id": order_id,
                    "days": tariff["days"]
                }
            })

            payment_url = payment.confirmation.confirmation_url

            # Сохраняем заказ только здесь
            save_order(order_id, chat_id, tariff["days"], tariff["price"])


    # ======= Сообщение с кнопками оплаты =======
            ctx.reply(
            f"💎 {tariff['name']}\nСтоимость: {tariff['price']} ₽\nВыберите способ оплаты 👇",
            keyboard=InlineKeyboard(
                [{"text": "💳 Банковская карта (IntellectMoney)", "url": intellectmoney_link_url}],
                [{"text": "💳 Банковская карта", "url": payment_url}],
                [{"text": "🟣 ЮMoney", "url": payment_url}],
                [{"text": "⚡ СБП", "url": payment_url}],
                [{"text": "🟢 SberPay", "url": payment_url}],
                [{"text": "❌ Отмена", "callback": "back"}]
            )
        )

        except Exception as e:
            ctx.reply("Ошибка при создании платежа ❌")
            log.error(f"Payment error: {e}")
        return




























    elif ctx.payload == "vip":
        chat_id = str(ctx.chat_id)
        profile = get_profile(chat_id)
        if not profile:
            ctx.reply("❗ Профиль не найден.")
            return
        if vip_active(profile):
            ctx.reply(
                f"💎 VIP уже активен!\n\n"
                f"📅 Действует до: {profile['vip_until']}\n\n"
                f"Вы можете продлить подписку:",
                keyboard=InlineKeyboard([
                    [{"text": "🔁 Продлить VIP", "callback": "vip_tariv"}],
                    [{"text": "⬅ Назад", "callback": "back"}]
                ])
            )
        else:
            ctx.reply(VIP_TEXT, keyboard=vip_start_keyboard)
            
    elif ctx.payload == "vip_tariv":
        ctx.reply("💎 Выберите тариф:", keyboard=vip_keyboard)








    elif ctx.payload == "vip_tarif":
        ctx.reply(
            "🔁 Выберите тариф для продления:",
            keyboard=vip_tarif_keyboard
        )
        return



    elif ctx.payload == "admin_panel":
        #Админ панель
        show_admin_panel(ctx)
    elif ctx.payload == "admin_vip_on":
        activate_vip(chat_id, 3650)
        show_admin_panel(ctx)

    elif ctx.payload == "admin_vip_off":
        remove_vip(chat_id)
        show_admin_panel(ctx)

    elif ctx.payload == "admin_refresh":
        show_admin_panel(ctx)

    elif ctx.payload == "admin_vip_on":
        activate_vip(chat_id, 3650)  # 10 лет фактически
        profile = get_profile(chat_id)
        ctx.reply("✅ VIP включён", keyboard=admin_keyboard(profile))
    elif ctx.payload == "admin_vip_off":
        remove_vip(chat_id)
        profile = get_profile(chat_id)
        ctx.reply("❌ VIP отключён", keyboard=admin_keyboard(profile))




    elif ctx.payload == "delete":
        # Пользователь хочет удалить профиль
        ctx.reply("Вы уверены, что хотите удалить анкету?", keyboard=delete_save_menu)
    elif ctx.payload == "edit":
        # Пользователь хочет редактировать профиль
        ctx.reply("Редактирование профиля:", keyboard=edit_keyboard)
    elif ctx.payload == "save":
        save_profile(chat_id, u)
        text, keyboard = invite_message(chat_id)
        ctx.reply(text, keyboard=keyboard)
    elif ctx.payload == "invite":
        text, keyboard = invite_message(chat_id)
        ctx.reply(text, keyboard=keyboard)

   
    
    elif ctx.payload == "delete_profile":
        # Пользователь хочет удалить профиль
        ctx.reply(
            "Анкета будет удалена через 30 дней.\n\n"
            "Вы уверены, что хотите удалить анкету?",
            keyboard=delete_confirm_keyboard
        )

    elif ctx.payload == "done_edit":
        # Сохраняем изменения и показываем меню редактирования
        save_profile(chat_id, u)  # сохраняем текущие данные пользователя
        ctx.reply("Изменения сохранены!", keyboard=edit_keyboard)  # показываем клавиатуру редактирования
   
    
    elif ctx.payload == "menu_delete":
        # Удаляем профиль полностью
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profiles WHERE user_id=?", (chat_id,))
        conn.commit()
        conn.close()

        # Удаляем данные из временной сессии
        users.pop(chat_id, None)

        # Сообщаем пользователю
        ctx.reply(
            "❌ Ваша анкета удалена полностью. Чтобы создать новую, перезапустите бота.",
            keyboard=None
        )    

    elif ctx.payload == "confirm_delete":
        # Помечаем профиль на удаление
        soft_delete_profile(chat_id)

        # Получаем профиль заново
        profile = get_profile(chat_id)

        # Отправляем сообщение о пометке на удаление с клавиатурой восстановления
        ctx.reply(
            "⚠️ Ваша анкета помечена на удаление. Восстановить?", 
            keyboard=restore_keyboard
        )

    elif ctx.payload == "cancel_delete":
        # Пользователь отказался от удаления профиля
        text, keyboard = main_menu(get_profile(chat_id), chat_id)
        ctx.reply(
                f"Удаление отменено ✅\n\n{text}",
                keyboard=keyboard
        )



    elif ctx.payload == "show_offer":
        # Пользователь запрашивает оферту
        ctx.reply(OFFER_TEXT, keyboard=vip_offer_keyboard)
    elif ctx.payload == "offer_accept":
        # Пользователь согласился с офертой
        ctx.reply("💎 Выбирайте тариф для подписки", keyboard=vip_keyboard)
    elif ctx.payload == "offer_decline":
        # Пользователь отказался от оферты
        profile = get_profile(chat_id)

        text, keyboard = main_menu(profile, chat_id)

        ctx.reply(
                "❌ Вы не приняли условия оферты.\n\n"
                "VIP-функции недоступны.\n\n"
                f"{text}",
                keyboard=keyboard
        )

    elif ctx.payload == "back":
        # Пользователь вернулся назад
        u["step"] = None
        text, keyboard = main_menu(get_profile(chat_id), chat_id)
        ctx.reply(text, keyboard=keyboard)
    elif ctx.payload == "main_menu":
        # Пользователь вернулся назад
        u["step"] = None
        text, keyboard = main_menu(get_profile(chat_id), chat_id)
        ctx.reply(text, keyboard=keyboard)



    # =========================
    #         СОЗДАНИЕ
    # =========================

    # ------------------ Колбеки для новой анкеты ------------------
    elif ctx.payload == "name":
        # Редактируем имя
        u["step"] = "name"
        ctx.reply("Введите имя:")
        
    elif ctx.payload in ("gender_m", "gender_f"):
        return process_gender_selection(ctx, chat_id, ctx.payload)

    elif ctx.payload == "birthdate":
        u["step"] = "birth_day"
        ctx.reply("Введите день рождения (1-31):")

    elif ctx.payload.startswith("city_selected:"):
        chat_id = str(ctx.chat_id)
        u = users.get(chat_id)
        if not u:
            print("[DEBUG] Пользователь не найден")
            return True

        is_saved = u.get("editing_existing", False)

        data = ctx.payload.replace("city_selected:", "")
        city, region = data.split("|")
        city_name = city.replace("_", " ")
        region_name = region.replace("_", "—") if region != "—" else ""

        u["city"] = city_name
        u["region"] = region_name

        # если это выбор города для фильтров
        if u.get("city_mode") == "filters":
            update_filter(chat_id, "filters_city",
                          f"{city_name} ({region_name})" if region_name else city_name)
            u["step"] = None
            u["city_mode"] = None
            show_filters(ctx)
            return True

        # редактирование существующей анкеты
        if is_saved:
            save_profile(chat_id, u)
            u["step"] = None
            u["is_editing"] = False
            ctx.reply(
                "Город обновлён ✅",
                keyboard=get_edit_keyboard(is_saved=True)
            )
        else:
            u["step"] = "about"
            ctx.reply(
                f"Город выбран {city_name} ({region_name})\nНапишите немного о себе:",
                keyboard=None
            )

        return True
        
    elif ctx.payload == "city":
        # Редактируем город
        u["step"] = "city_search"
        ctx.reply("Введите город:")

    elif ctx.payload == "about":
        # Редактируем “О себе”
        u["step"] = "about"
        ctx.reply("Напишите о себе:")

    elif ctx.payload == "photo":
        # Редактируем фото
        u["step"] = "photo"
        ctx.reply("Пришлите фото (картинка или ссылка):")


    # =========================
    #         РЕДАКТИРОВАНИЕ
    # =========================


    #--------Имя
    elif ctx.payload in ("edit_name_save", "edit_name_profile"):
        u["step"] = "edit_name"
        u["editing_existing"] = ctx.payload.endswith("_profile")
        u["is_editing"] = True
        ctx.reply("Введите имя:")

# ------------------ Редактирование пола ------------------
    # ------------------ Кнопки "редактировать пол" ------------------
    elif ctx.payload in ("edit_gender_save", "edit_gender_profile"):
        chat_id = str(ctx.chat_id)
        users.setdefault(chat_id, {"step": None, "mode": None})
        u = users[chat_id]

        # Включаем режим редактирования
        u["mode"] = "edit"
        u["step"] = "gender_select"
        u["is_editing"] = True
        u["editing_existing"] = ctx.payload.endswith("_profile")
        u["return_keyboard"] = ctx.payload  # чтобы потом открыть правильную клавиатуру

        ctx.reply("Выберите пол:", keyboard=gender_keyboard)
        return True

    # ------------------ Выбор пола ------------------
    elif ctx.payload in ("gender_m", "gender_f"):
        chat_id = str(ctx.chat_id)
        u = users.get(chat_id)
        if not u:
            return True
        # используем универсальную функцию
        return process_gender_selection(ctx, chat_id, ctx.payload)



       
# ------------------ Колбек для редактирования даты рождения ------------------
    elif ctx.payload in ("edit_birthdate_save", "edit_birthdate_profile"):
        print(f"[DEBUG CALLBACK] Нажата кнопка редактирования даты рождения, payload={ctx.payload}")

        chat_id = str(ctx.chat_id)
        users.setdefault(chat_id, {"step": None})
        u = users[chat_id]

        u["step"] = "edit_birth_day"
        u["is_editing"] = True  # <- важно, чтобы text_steps шёл в handle_profile_edit
        u["editing_existing"] = ctx.payload.endswith("_profile")

        print(f"[DEBUG] Шаг установлен: {u['step']}, редактируем существующую анкету: {u['editing_existing']}")

        ctx.reply("Введите день рождения (1-31):")  
    
    
    
    
# ------------------ Колбек для редактирования города ------------------    


    elif ctx.payload in ("edit_city_save", "edit_city_profile"):
        print(f"[DEBUG CALLBACK] Нажата кнопка редактирования города: {ctx.payload}")

        u["step"] = "edit_city_search_"
        u["is_editing"] = True
        u["editing_existing"] = ctx.payload.endswith("_profile")

        ctx.reply("Введите название города:")
        return True     

        
        

# Колбек для редактирования "О себе"
    # ------------------ О себе ------------------
    elif ctx.payload in ("edit_about_save", "edit_about_profile"):
        chat_id = str(ctx.chat_id)
        users.setdefault(chat_id, {"step": None})
        u = users[chat_id]
        u["step"] = "edit_about"
        u["is_editing"] = True
        u["editing_existing"] = ctx.payload.endswith("_profile")
        ctx.reply("Напишите о себе:")


# ------------------ Фото ------------------
    elif ctx.payload in ("edit_photo_save", "edit_photo_profile"):
        print(f"[DEBUG CALLBACK] Нажата кнопка редактирования фото, payload={ctx.payload}")

        chat_id = str(ctx.chat_id)
        users.setdefault(chat_id, {"step": None})
        u = users[chat_id]

        u["step"] = "edit_photo"
        u["is_editing"] = True
        u["editing_existing"] = ctx.payload.endswith("_profile")

        print(f"[DEBUG] Шаг установлен: {u['step']}, редактируем существующую анкету: {u['editing_existing']}")

        ctx.reply("Отправьте новое фото:")



    # =========================
    #         ФИЛЬТРЫ
    # =========================

    elif ctx.payload == "open_filters":
        show_filters(ctx)

    elif ctx.payload == "gender_filters":
        ctx.reply("Выберите пол:", keyboard=gender_filters)

    elif ctx.payload == "age_filters":
        profile = get_profile(chat_id) or {}
        min_age = profile.get("filters_age_min", MIN_AGE_LIMIT)
        max_age = profile.get("filters_age_max", MAX_AGE_LIMIT)

        ctx.reply(
            "Выберите возраст:",
            keyboard=age_keyboard_filters(min_age, max_age)
        )

    elif ctx.payload == "city_filters":
        u["step"] = "city_search"
        u["city_mode"] = "filters"
        ctx.reply("Введите первые буквы города:")

    elif ctx.payload == "done_filters":
        profile = get_profile(chat_id)
        show_filters(ctx)  # Показываем фильтры заново с текущими значениями

    elif ctx.payload in (
        "gender_filter_m",
        "gender_filter_f",
        "gender_filter_any"
    ):

        value = {
            "gender_filter_m": "М",
            "gender_filter_f": "Ж",
            "gender_filter_any": "Любой"
        }[ctx.payload]

        update_filter(chat_id, "filters_gender", value)

        show_filters(ctx)

    elif ctx.payload in (
        "age_min_minus", "age_min_plus",
        "age_max_minus", "age_max_plus"
    ):

        profile = get_profile(chat_id) or {}
        min_age = profile.get("filters_age_min", MIN_AGE_LIMIT)
        max_age = profile.get("filters_age_max", MAX_AGE_LIMIT)

        if ctx.payload == "age_min_minus":
            min_age = max(MIN_AGE_LIMIT, min_age - 1)
        elif ctx.payload == "age_min_plus":
            min_age = min(max_age, min_age + 1)
        elif ctx.payload == "age_max_minus":
            max_age = max(min_age, max_age - 1)
        elif ctx.payload == "age_max_plus":
            max_age = min(MAX_AGE_LIMIT, max_age + 1)

        update_filter(chat_id, "filters_age_min", min_age)
        update_filter(chat_id, "filters_age_max", max_age)

        ctx.reply(
            "Выберите возраст:",
            keyboard=age_keyboard_filters(min_age, max_age)
        )
















    elif ctx.payload == "back_to_menu":
        # Возвращение в главное меню
        u["step"] = None
        text, keyboard = main_menu(get_profile(chat_id), chat_id)
        ctx.reply(text, keyboard=keyboard)
    elif ctx.payload == "edit_profile":
        # Переход в режим редактирования профиля
        ctx.reply("Что вы хотите изменить?", keyboard=get_edit_keyboard(is_saved=False))
    elif ctx.payload == "edit_profile_after_creation":
        u["step_edit"] = True
        u["step"] = None
        ctx.reply("Что вы хотите изменить?", keyboard=get_edit_keyboard(is_saved=True))


    elif ctx.payload == "ruletka":
        # Запуск чата-рулетки
        ctx.reply(
            "💬 Чат-рулетка готова. Выберите действие:",
            keyboard=ruletka_keyboard
        )
    elif ctx.payload == "roulette_in":
        asyncio.create_task(roulette_in(ctx))



    elif ctx.payload == "roulette_out":
        asyncio.create_task(roulette_out(str(ctx.chat_id)))







    elif ctx.payload == "vip_tariv":
        # Просмотр тарифов VIP
        ctx.reply("💎 Выберите тариф для подписки", keyboard=vip_keyboard)
    
    
    
    elif ctx.payload == "restore_profile":
        profile = get_profile(chat_id)

        if profile and profile.get("deleted_at"):
                # Снимаем пометку удаления
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(
                        "UPDATE profiles SET deleted_at=NULL WHERE user_id=?",
                        (chat_id,)
                )
                conn.commit()
                conn.close()

                # Получаем обновлённый профиль
                profile = get_profile(chat_id)

                text, keyboard = main_menu(profile, chat_id)
                ctx.reply(
                        f"♻ Ваша анкета восстановлена!\n\n{text}",
                        keyboard=keyboard
                )
        else:
                text, keyboard = main_menu(profile, chat_id)
                ctx.reply(
                        f"Анкета не была удалена или уже восстановлена.\n\n{text}",
                        keyboard=keyboard
                )



    elif ctx.payload == "cancel_restore":
        # Пользователь отказался восстановить
        ctx.reply("❌ Анкета не восстановлена.", keyboard=restore_keyboard)

    
    


    elif ctx.payload == "admin_timer":
        current = get_chat_timer()
        ctx.reply(
            f"⏳ Текущий таймер: {current} сек.\n"
            "Введите новое значение:"
        )
        user_states[str(ctx.chat_id)] = "waiting_timer"
    elif payload == "age_yes":
        users[chat_id]["step"] = "name"
        ctx.reply("✅ Отлично! Продолжаем…\nВведите ваше имя:")
    elif payload == "age_no":
        ctx.reply("🚫 К сожалению, доступ запрещён.")
    elif payload == "restore_profile":
        ctx.reply("✅ Анкета восстановлена!")
        
    # ------------------ Кнопка Готово ------------------
    elif ctx.payload in ("edit_save_profile", "edit_done_create", "open_profile", "cancel_menu_delete"):
        print(f"[DEBUG CALLBACK] Нажата кнопка Готово, payload={ctx.payload}")

        chat_id = str(ctx.chat_id)
        u = users.get(chat_id, {})
        u["step"] = None
        u["is_editing"] = False

        # Сохраняем профиль
        save_profile(chat_id, u)
        print(f"[DEBUG CALLBACK] Профиль сохранён для chat_id={chat_id}")

        # Получаем обновлённый профиль
        user_profile = get_profile(chat_id)
        print(f"[DEBUG CALLBACK] user_profile загружен: {user_profile}")

        # ------------------ Готово 2 ------------------
        if ctx.payload in ("edit_save_profile", "cancel_menu_delete"):
            print("[DEBUG CALLBACK] Показываем save_menu")
            keyboard = save_menu  # если это объект
            # keyboard = save_menu(user_profile)  # если это функция
            show_profile(ctx, user_profile, keyboard)

        # ------------------ Готово 1 ------------------
        else:
            print("[DEBUG CALLBACK] Показываем profile_menu")
            keyboard = profile_menu  # если объект
            # keyboard = profile_menu(user_profile)  # если это функция
            show_profile(ctx, user_profile, keyboard)

        return True


        
        
        
        
    else:
        print("Необработанный колбэк:", ctx.payload)
		
 

        
        
        




# ================== РУЛЕТКА ==================
@bot.command("roulette")

# ================== ТАЙМЕР ==================
# ================== ТАЙМЕР ЧАТА ==================
async def chat_timer(u1, u2):
    timer_seconds = get_chat_timer()
    await asyncio.sleep(timer_seconds)

    # Проверка, что чат всё ещё активен
    if active_chats.get(u1) != u2:
        return

    p1 = get_profile(u1)
    p2 = get_profile(u2)
    if not p1 or not p2:
        return

    # VIP освобождает от таймера
    if is_vip(p1) or is_vip(p2):
        return

    # Закрываем чат
    active_chats.pop(u1, None)
    active_chats.pop(u2, None)

    minutes_str = minutes_text(timer_seconds)

    # Сообщения для пользователей
    msg1 = (
        f"⏳ Бесплатные {minutes_str} закончились!\n\n"
        f"💬 {p2.get('name')} всё ещё онлайн...\n"
        f"Не упусти шанс продолжить разговор 🔥\n\n"
        f"💎 Активируй VIP и общайся без ограничений:"
    )
    msg2 = (
        f"⏳ Бесплатные {minutes_str} закончились!\n\n"
        f"💬 {p1.get('name')} всё ещё онлайн...\n"
        f"Не упусти шанс продолжить разговор 🔥\n\n"
        f"💎 Активируй VIP и общайся без ограничений:"
    )

    # Исправленный формат клавиатуры (список словарей, не вложенные списки)
    keyboard = InlineKeyboard(
        [{"text": "💎 Продолжить без ограничений", "callback": "vip"}],  # первая строка
        [
            {"text": "🔄 Найти нового собеседника", "callback": "ruletka"},
            {"text": "📩 Пригласить друга 🎁", "callback": "invite"}
        ]  # вторая строка с двумя кнопками
    )

    # Отправка первого сообщения (без ошибок)
    if u1 in contexts:
        contexts[u1].reply(msg1)  # 🔹 клавиатуру не прикрепляем
    if u2 in contexts:
        contexts[u2].reply(msg2)  # 🔹 клавиатуру не прикрепляем

    # Небольшая пауза перед повторным напоминанием
    await asyncio.sleep(2)

    # Второе напоминание с клавиатурой
    reminder1 = (
        f"🔥 {p2.get('name')} всё ещё онлайн! "
        f"Активируйте VIP и не упустите разговор!\n"
    )
    reminder2 = (
        f"🔥 {p1.get('name')} всё ещё онлайн! "
        f"Активируйте VIP и не упустите разговор!\n"
    )

    if u1 in contexts:
        contexts[u1].reply(reminder1, keyboard=keyboard)  # 🔹 с клавиатурой
    if u2 in contexts:
        contexts[u2].reply(reminder2, keyboard=keyboard)  # 🔹 с клавиатурой



# ================== roulette_in ==================

async def roulette_in(ctx):
    user_id = str(ctx.chat_id)
    
    print(f"[SEARCH START] {user_id}") 
    
    contexts[user_id] = ctx
    profile = get_profile(user_id)

    if not profile:
        ctx.reply("❗ Профиль не найден. Сначала заполните анкету.")
        return

    filters = get_filters(user_id)
    print(f"[USER FILTERS] {user_id}: {filters}")
    if not filters or not filters.get("city"):
        ctx.reply("❗ Выберите город в фильтрах")
        return

    if user_id in active_chats:
        ctx.reply("❗ Вы уже в чате")
        return

    # Добавляем в очередь VIP вперед, обычные — в конец
    if is_vip(profile):
        await redis_client.lpush(QUEUE_KEY, user_id)
    else:
        await redis_client.rpush(QUEUE_KEY, user_id)

    ctx.reply("🔎 Ищем собеседника...", keyboard=ruletka_keyboard)

    # Поиск партнёра
    while True:
        if user_id in active_chats:
            print(f"[STOP SEARCH] {user_id} уже в чате")
            break
    
        if user_id in active_chats:
            print(f"[STOP SEARCH] {user_id} уже в чате")
            break
    
        candidates = await redis_client.lrange(QUEUE_KEY, 0, -1)
        partner_id = None

        for candidate in candidates:
            if candidate == user_id:
                continue

            partner_profile = get_profile(candidate)
            partner_filters = get_filters(candidate)

            if not partner_profile or not partner_filters:
                continue

            # === Фильтры города и пола ===
            partner_city_filter = partner_filters.get("city")
            user_city_filter = filters.get("city")

            if partner_city_filter != "Любой" and partner_city_filter != profile.get("city"):
                continue

            if user_city_filter != "Любой" and user_city_filter != partner_profile.get("city"):
                continue
            
            
            
            
            #if partner_filters.get("city") != profile.get("city"):
            #    continue
            if partner_filters.get("gender") and partner_filters.get("gender") != "Любой":
                if profile.get("gender") != partner_filters.get("gender"):
                    continue

            # === Фильтры возраста (двусторонние) ===
            user_age = profile.get("age", 0)
            partner_age = partner_profile.get("age", 0)

            user_age_min = filters.get("age_min", 0)
            user_age_max = filters.get("age_max", 0)
            partner_age_min = partner_filters.get("age_min", 0)
            partner_age_max = partner_filters.get("age_max", 0)

            if not (user_age_min <= partner_age <= user_age_max):
                continue
            if not (partner_age_min <= user_age <= partner_age_max):
                continue

            partner_id = candidate
            break

        if partner_id:
            # Удаляем из очереди
            await redis_client.lrem(QUEUE_KEY, 0, partner_id)
            await redis_client.lrem(QUEUE_KEY, 0, user_id)

            # === Лог и уведомления ===
            log.info(f"[Connect] {user_id} ↔ {partner_id}")
            ctx.reply("✨ Собеседник найден! Начните общение 👋")
            if partner_id in contexts:
                contexts[partner_id].reply("✨ Собеседник найден! Начните общение 👋")

            # Получаем профили для анкет
            user_profile = get_profile(user_id)
            partner_profile = get_profile(partner_id)

            leave_keyboard = InlineKeyboard(
                [{"text": "⏹ Выйти из чата", "callback": "leave_chat"}]
            )

            # Анкета партнёра для пользователя
            if partner_profile:
                show_profile(ctx, partner_profile, keyboard=leave_keyboard)

            # Анкета пользователя для партнёра
            if user_profile and partner_id in contexts:
                show_profile(contexts[partner_id], user_profile, keyboard=leave_keyboard)
            # Запускаем чат
            print(f"[CONNECT] {user_id} ↔ {partner_id}") 
            await start_chat(user_id, partner_id)
            # Запускаем таймер в фоне
            asyncio.create_task(chat_timer(user_id, partner_id))
            break

        else:
            # Если очередь пуста, ждём 1 сек
            await asyncio.sleep(1)

# ================== ВЫХОД ==================
async def roulette_out(user_id):
    partner = active_chats.get(user_id)

    # ===== Если пользователь уже не в чате =====
    if not partner:
        if user_id in contexts:
            profile = get_profile(user_id)
            header_text, keyboard = main_menu(profile, user_id)

            final_text = f"❌ Вы не в чате\n\n{header_text}"
            contexts[user_id].reply(final_text, keyboard=keyboard)
        return

    # ===== Удаляем обоих из активных чатов =====
    active_chats.pop(user_id, None)
    active_chats.pop(partner, None)

    # ===== Пользователь =====
    if user_id in contexts:
        profile = get_profile(user_id)
        header_text, keyboard = main_menu(profile, user_id)

        final_text = f"❌ Вы вышли из чата\n\n{header_text}"
        contexts[user_id].reply(final_text, keyboard=keyboard)

    # ===== Партнёр =====
    if partner in contexts:
        profile = get_profile(partner)
        header_text, keyboard = main_menu(profile, partner)

        final_text = f"❗ Собеседник вышел из чата\n\n{header_text}"
        contexts[partner].reply(final_text, keyboard=keyboard)

    # ===== Очистка памяти =====
    contexts.pop(user_id, None)
    contexts.pop(partner, None)

# ================== АДМИН ПАНЕЛЬ ==================








# ================== Админ панель ==================
@bot.command("admin")
def show_admin_panel(ctx):
    if str(ctx.chat_id) != str(ADMIN_ID):
        ctx.reply("⛔ Доступ запрещён")
        return

    stats = get_stats()
    profile = get_profile(ctx.chat_id)

    text = (
        "📊 *Админ-панель*\n\n"
        "👥 Пользователи:\n"
        f"• Всего: {stats['users_total']}\n"
        f"• Мужчин: {stats['users_m']}\n"
        f"• Женщин: {stats['users_f']}\n\n"
        "💎 VIP подписка:\n"
        f"• Всего VIP: {stats['vip_total']}\n"
        f"• Мужчин VIP: {stats['vip_m']}\n"
        f"• Женщин VIP: {stats['vip_f']}\n\n"
        "🎰 Рулетка:\n"
        f"🟢 Онлайн: {stats['online']}\n"
        f"⏳ В очереди: {stats['waiting_queue']}\n"
        f"💬 Активных чатов: {stats['active_chats']}\n"
        f"🔎 Поисков всего: {stats['total_searches']}\n"
        f"🎉 Совпадений: {stats['total_matches']}"
    )


    ctx.reply(text, keyboard=admin_keyboard(profile))


    # ------------------ Кнопки ------------------

    
def admin_keyboard(profile):
    if is_vip(profile):
        vip_button = {"text": "❌ Отключить VIP (у меня)", "callback": "admin_vip_off"}
    else:
        vip_button = {"text": "✅ Включить VIP (у меня)", "callback": "admin_vip_on"}

    return InlineKeyboard(
        [vip_button],
        [{"text": "⏳ Таймер чата", "callback": "admin_timer"}],    
        [{"text": "🔄 Обновить", "callback": "admin_refresh"}],
        [{"text": "⬅ Назад", "callback": "back"}]
    )





# ================== Функция статистики ==================
# ================== Функция статистики ==================
def get_stats():
    now = int(time.time())
    stats = {}

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # ================== ПОЛЬЗОВАТЕЛИ ==================
    cursor.execute("SELECT COUNT(*) FROM profiles")
    stats["users_total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM profiles WHERE gender='М'")
    stats["users_m"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM profiles WHERE gender='Ж'")
    stats["users_f"] = cursor.fetchone()[0]

    # ================== VIP ==================
    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE vip_until IS NOT NULL AND vip_until > ?",
        (now,)
    )
    stats["vip_total"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE gender='М' AND vip_until IS NOT NULL AND vip_until > ?",
        (now,)
    )
    stats["vip_m"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE gender='Ж' AND vip_until IS NOT NULL AND vip_until > ?",
        (now,)
    )
    stats["vip_f"] = cursor.fetchone()[0]

    # ================== ОНЛАЙН ==================
    online_limit = now - 300
    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE last_activity IS NOT NULL AND last_activity > ?",
        (online_limit,)
    )
    stats["online"] = cursor.fetchone()[0]


    # ================== РУЛЕТКА ==================
    # ⚠ Поменяй названия таблиц если у тебя другие!

    # В очереди
    cursor.execute("SELECT COUNT(*) FROM roulette_queue")
    stats["waiting_queue"] = cursor.fetchone()[0]

    # Активные чаты
    cursor.execute("SELECT COUNT(*) FROM active_chats")
    stats["active_chats"] = cursor.fetchone()[0]

    # Всего поисков
    cursor.execute("SELECT COUNT(*) FROM search_history")
    stats["total_searches"] = cursor.fetchone()[0]

    # Всего совпадений
    cursor.execute("SELECT COUNT(*) FROM match_history")
    stats["total_matches"] = cursor.fetchone()[0]

    conn.close()
    return stats

def ensure_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO roulette_stats (user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()
    conn.close()

def log_search(user_id):
    ensure_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE roulette_stats SET searches = searches + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def log_match(user_id):
    ensure_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE roulette_stats SET matches = matches + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def log_chat_started(user_id):
    ensure_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE roulette_stats SET chats_started = chats_started + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def log_chat_ended(user_id):
    ensure_stats(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE roulette_stats SET chats_ended = chats_ended + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# Обработчик ввода нового значения таймера
@bot.on("timerullete")
def handle_timer_message(ctx):
    chat_id = str(ctx.chat_id)
    text = ctx.text

    if user_states.get(chat_id) == "waiting_timer_value":
        log.debug("Обработка таймера началась")
        if not text.isdigit():
            ctx.reply("❌ Введённое значение не является числом. Повторите попытку.")
            return

        seconds = int(text)
        if seconds < 10:
            ctx.reply("Минимальное значение таймера — 10 секунд.")
            return

        set_chat_timer(seconds)
        ctx.reply(f"✅ Новый таймер установлен: {seconds} секунд", keyboard=admin_menu())
        user_states.pop(chat_id, None)
        log.debug("Обработка таймера закончилась")











    




# Главная функция старта
if __name__ == "__main__":
    init_db()
    print("🚀 Bot started")
    bot.run()