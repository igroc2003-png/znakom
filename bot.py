import sqlite3
import logging
import threading
import time
from datetime import datetime
from maxgram import Bot
from maxgram.keyboards import InlineKeyboard
from config import TOKEN, ADMIN_ID, SUPPORT_URL, IM_ESHOP_ID, IM_SECRET_KEY, IM_TEST
import hashlib
import urllib.parse
import sys
import subprocess
from payment import create_payment_link

# ================== ЛОГИ ==================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - BOT - %(levelname)s - %(message)s"
)
log = logging.getLogger("BOT")


# ================== ИНИЦИАЛИЗАЦИЯ БОТА ==================
bot = Bot(TOKEN)

# ================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==================
GEO_DB = "geo.db"
DB_FILE = "profiles.db"        # Используем существующую таблицу профилей
users = {}                     # Временные данные при заполнении анкеты
queue = []                     # Очередь для игры в рулетку
active_chats = {}              # Активные чаты рулетки: user_id -> partner_id
contexts = {}                  # Контексты пользователей для рулетки: user_id -> ctx
chat_started_at = {}           # 👈 ВАЖНО (у тебя из-за этого была ошибка)
buh_process = None             # глобальная переменная для процесса buh.py
# ================== КЛАВИАТУРЫ ==================

# Главное меню анкеты
def main_menu(profile=None, chat_id=None):
    """
    Формирует главное меню для пользователя.
    profile — словарь профиля (может быть None)
    chat_id — id пользователя (может быть None, тогда берется из profile)
    """

    # Если chat_id не передан, пробуем взять из profile
    if not chat_id and profile:
        chat_id = profile.get("user_id")

    # Выбираем эмодзи по полу
    emoji = "👤"
    if profile:
        if profile.get("gender") == "М":
            emoji = "👨"
        elif profile.get("gender") == "Ж":
            emoji = "👩"

    buttons = [
        [{"text": "⭐ VIP", "callback": "vip"}],
        [{"text": f"{emoji} Анкета", "callback": "open_profile"}],
        [{"text": "🎯 Фильтры", "callback": "open_filters"}],
        [{"text": "🎲 Рулетка", "callback": "ruletka"}],
        [{"text": "🆘 Поддержка", "url": SUPPORT_URL}],
    ]

    # Добавляем кнопку админ-панель только если chat_id соответствует ADMIN_ID
    if chat_id and str(chat_id) == str(ADMIN_ID):
        buttons.append([{"text": "⚙ Админ панель", "callback": "admin_panel"}])

    return InlineKeyboard(*buttons)


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


# Клавиатура оферты

vip_offer_keyboard = InlineKeyboard(
    [{"text": "✅ Согласен", "callback": "offer_accept"}],
    [{"text": "❌ Не согласен", "callback": "offer_decline"}]
)

 

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

# Меню редактирования анкеты
edit_keyboard = InlineKeyboard(
    [{"text": "📝 Имя", "callback": "edit_name"},
     {"text": "⚧ Пол", "callback": "edit_gender"}],
    [{"text": "🎂 Дата рождения", "callback": "edit_birthdate"},
     {"text": "🏙 Город", "callback": "edit_city"}],
    [{"text": "✍️ О себе", "callback": "edit_about"},
     {"text": "📸 Фото", "callback": "edit_photo"}],
    [{"text": "👍 Готово", "callback": "edit_done"}]
)

# Меню редактирования анкеты
edit_save = InlineKeyboard(
    [{"text": "📝 Имя", "callback": "edit_name"},
     {"text": "⚧ Пол", "callback": "edit_gender"}],
    [{"text": "🎂 Дата рождения", "callback": "edit_birthdate"},
     {"text": "🏙 Город", "callback": "edit_city"}],
    [{"text": "✍️ О себе", "callback": "edit_about"},
     {"text": "📸 Фото", "callback": "edit_photo"}],
    [{"text": "👍 Готово", "callback": "edit_save"}]
)

# Меню после заполнения анкеты
save_menu = InlineKeyboard([
    {"text": "💾 Сохранить ✅", "callback": "save"},
    {"text": "✏️ Редактировать", "callback": "edit"},
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





# Фильтры
MIN_AGE_LIMIT = 18
MAX_AGE_LIMIT = 100

# Главное меню фильтров
# Главное меню фильтров
def keyboard_filters(profile=None):
    return InlineKeyboard(
        [
            {"text": "Пол", "callback": "gender_filters"},
            {"text": "Возраст", "callback": "age_filters"},
            {"text": "Город", "callback": "city_filters"},
        ],
        [
            {"text": "Готово 👍", "callback": "done_filters"}
        ]
    )

# Пол фильтр
gender_filters = InlineKeyboard(
    [
        {"text": "👨 Мужской", "callback": "gender_filter_m"},
        {"text": "👩 Женский", "callback": "gender_filter_f"}
    ],
    [
        {"text": "🎭 Любой", "callback": "gender_filter_any"}
    ]
)




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
            {"text": "✅ Готово", "callback": "done_edit"}
        ]
    )


# Клавиатура VIP
def vip_menu():
    return InlineKeyboard(
        [{"text": "💎 Оформить VIP", "callback": "vip"}],
        [{"text": "⬅️ В меню", "callback": "back"}]
    )




# Клавиатура рулетки
ruletka_keyboard = InlineKeyboard(
    [{"text": "▶ Найти собеседника", "callback": "roulette"}],
    [{"text": "⏹ Выйти из чата", "callback": "leave_chat"}]
)

# ================== БАЗА ДАННЫХ ==================
def create_db():
    conn = sqlite3.connect(DB_FILE)
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
            region TEXT,
            about TEXT,
            photo_url TEXT,
            is_vip INTEGER DEFAULT 0,
            vip_until INTEGER DEFAULT NULL,
            deleted_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            filters_gender TEXT DEFAULT 'Любой',
            filters_age_min INTEGER DEFAULT 18,
            filters_age_max INTEGER DEFAULT 35,
            filters_city TEXT DEFAULT 'Любой',
            filters_region TEXT DEFAULT 'Любой',
            is_subscribed INTEGER DEFAULT 0,
            subscription_expire INTEGER DEFAULT NULL
        );
    """)
    conn.commit()
    conn.close()
 
#Удаление анкеты через 30 дней
def delete_expired_profiles():
    now = datetime.now().timestamp()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM profiles WHERE deleted_at IS NOT NULL AND deleted_at <= ?",
        (now,)
    )
    conn.commit()
    conn.close()

 
def update_filter(user_id, field, value):
      conn = sqlite3.connect(DB_FILE)
      cursor = conn.cursor()
      cursor.execute(
          f"UPDATE profiles SET {field}=? WHERE user_id=?",
          (value, user_id)
      )
      conn.commit()
      conn.close()
      log.info(f"🔧 filter {field}={value} saved for {user_id}")
    
def delete_profile(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# Получить профиль пользователя
def get_profile(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # 🔥 ВОТ ЭТО ГЛАВНОЕ
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM profiles WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


# Сохранить профиль пользователя
def save_profile(user_id, data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO profiles (
            user_id, name, gender, birthdate, age, zodiac, city, region, about, photo_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        user_id,
        data.get("name"),
        data.get("gender"),
        data.get("birthdate"),
        data.get("age"),
        data.get("zodiac"),
        data.get("city"),  # Город сохраняется в поле city
        data.get("region"),  # Регион сохраняется в поле region
        data.get("about"),
        data.get("photo_url")
    ))
    conn.commit()
    conn.close()

#пометка удаления    
def soft_delete_profile(user_id):
    delete_date = datetime.now().timestamp() + 30 * 24 * 60 * 60  # +30 дней в секундах

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE profiles SET deleted_at = ? WHERE user_id = ?",
        (delete_date, user_id)
    )
    conn.commit()
    conn.close()
  

# ================== УНИВЕРСАЛЬНЫЙ ВЫБОР ГОРОДА ==================
def send_city_selection(ctx, text, limit=5):
    """
    Безопасная функция поиска города и отправки клавиатуры выбора.
    Проверяет: 
    - минимум 2 символа в запросе,
    - нормализует первую букву в заглавную,
    - формирует клавиатуру выбора,
    - ограничивает список городов лимитом (по умолчанию 5 для фильтров).
    """
    chat_id = str(ctx.chat_id)

    if len(text.strip()) < 2:
        ctx.reply("Введите минимум 2 символа")
        return

    # Нормализация первой буквы
    normalized = text.strip()[0].upper() + text.strip()[1:].lower()

    try:
        conn = sqlite3.connect(GEO_DB)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, region FROM geo WHERE name LIKE ? ORDER BY name LIMIT ?",
            (normalized + "%", limit)
        )
        cities = cursor.fetchall()
        conn.close()
    except Exception as e:
        ctx.reply(f"Ошибка базы данных: {e}")
        return

    if not cities:
        ctx.reply("Города не найдены, попробуйте ещё")
        return

    # Формируем безопасные кнопки
    kb_rows = []
    for name, region in cities:
        safe_callback = f"city_selected:{name.replace(' ', '_').replace(':', '_')}|{region.replace(' ', '_')}"
        kb_rows.append([{"text": f"{name} ({region})", "callback": safe_callback}])

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

# ================== ОБРАБОТКА ПРОФИЛЯ ==================
def show_profile(ctx, profile, keyboard):
    emoji = "👨" if profile.get("gender") == "М" else "👩"
    text = (
        f"{emoji} Ваша анкета:\n\n"
        f"Имя: {profile.get('name')}\n"
        f"Пол: {profile.get('gender')}\n"
        f"🎂 Дата рождения: {profile.get('birthdate')}\n"
        f"🎈 Возраст: {profile.get('age')}\n"
        f"🏙 Город: {profile.get('city')}\n"
        f"✍️ О себе: {profile.get('about')}\n\n"
        f"💎 VIP: {'да' if profile.get('is_vip') else 'нет'}\n"
        f"📸 Фото:\n{profile.get('photo_url')}"
    )
    
    ctx.reply(text, keyboard=keyboard)

def show_filters(ctx):
      profile = get_profile(ctx.chat_id)
      if not profile:
          ctx.reply("Фильтры не найдены")
          return

      gender = profile.get("filters_gender") or "Любой"
      min_age = profile.get("filters_age_min") or MIN_AGE_LIMIT
      max_age = profile.get("filters_age_max") or MAX_AGE_LIMIT
      city = profile.get("filters_city") or "Любой"

      emoji = "👨" if gender == "М" else "👩" if gender == "Ж" else "🎭"

      text = (
          f"⚙️ Ваши фильтры:\n\n"
          f"Пол: {gender} {emoji}\n"
          f"Возраст: {min_age}–{max_age}\n"
          f"Город: {city}"
      )

      ctx.reply(text, keyboard=keyboard_filters(profile))















def is_vip(profile):
    if not profile:
        return False

    vip_until = profile.get("vip_until")
    if not vip_until:
        return False

    if vip_until > int(time.time()):
        return True

    return False


def chat_timer(u1, u2):
    time.sleep(180)

    if active_chats.get(u1) != u2:
        return

    p1 = get_profile(u1)
    p2 = get_profile(u2)

    if is_vip(p1) or is_vip(p2):
        return

    active_chats.pop(u1, None)
    active_chats.pop(u2, None)

    chat_started_at.pop(u1, None)
    chat_started_at.pop(u2, None)

    msg = (
        "⏳ Общение завершено (3 минуты)\n\n"
        "💎 Оформите VIP для общения без ограничений"
    )

    if u1 in contexts:
        contexts[u1].reply(msg, keyboard=vip_menu())
    if u2 in contexts:
        contexts[u2].reply(msg, keyboard=vip_menu())



# Функция для автоматического отключения чата
def auto_leave_if_non_vip(user_id, partner_id):
    time.sleep(180)  # Ждём 3 минуты (180 секунд)
    profile = get_profile(user_id)
    partner_profile = get_profile(partner_id)

    # Проверка на None
    if profile is None or partner_profile is None:
        return

    if not is_vip(profile) and not partner_is_vip(profile):
        if user_id in active_chats and active_chats[user_id] == partner_id:
            del active_chats[user_id]
            del active_chats[partner_id]
            ctx = contexts.get(user_id)
            p_ctx = contexts.get(partner_id)
            if ctx:
                ctx.reply("Время истекло. Оба участника не имеют VIP-статус, поэтому чат автоматически закрыт.")
            if p_ctx:
                p_ctx.reply("Время истекло. Оба участника не имеют VIP-статус, поэтому чат автоматически закрыт.")

 




def intellectmoney_link(order_id: str, amount: float, client_email: str) -> str:
    """
    Генерация ссылки для выставления счета через IntellectMoney.
        
    :param order_id: Внутренний номер заказа
    :param amount: Сумма в рублях (1 – 3 500 000)
    :param client_email: Email пользователя
    :return: Ссылка на оплату
    """
    # Проверка диапазона суммы
    if amount < 1 or amount > 3500000:
        raise ValueError("Сумма оплаты должна быть от 1 до 3 500 000 ₽")

    base_url = "https://merchant.intellectmoney.ru/"
    params = {
        "eshopId": IM_ESHOP_ID,       # обязательно
        "orderId": order_id,          # внутренний номер заказа
        "recipientAmount": f"{amount:.2f}",  # обязательно!
        "recipientCurrency": "RUB",   # валюта
        "ClientEmail": client_email,
        "TestMode": 1                 # 1 — тест, 0 — реальный платеж
    }

    query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return f"{base_url}?{query_string}"










 
# ================== ОБРАБОТКА ВВОДА ГОРОДА ==================
@bot.on("message_created")
def relay(ctx):
    user_id = str(ctx.chat_id)
    contexts[user_id] = ctx
	
	# Сначала обрабатываем шаги анкеты
    text_steps(ctx)
    

    # ❗ Если это callback — выходим
    if ctx.payload:
        return

    if user_id not in active_chats:
        return

    partner_id = active_chats[user_id]

    text = ctx.message.get("body", {}).get("text")
    if not text:
        return

    log.info(f"[Relay] {user_id} -> {partner_id}: {text}")

    if partner_id in contexts:
        contexts[partner_id].reply(text)

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

# Логика шагов анкеты
def text_steps(ctx):
    chat_id = str(ctx.chat_id)
    users.setdefault(chat_id, {"step": None})
    u = users[chat_id]
    step = u.get("step")
    if not step:
        return

    text = ctx.message.get("text") or ctx.message.get("body", {}).get("text", "")
    attachments = ctx.message.get("body", {}).get("attachments", [])



    # -------- Имя --------
    if step == "name":
        if not text:
            ctx.reply("Введите имя текстом")
            return
        u["name"] = text
        if u.get("step_edit"):
            u["step"] = "edit"
            ctx.reply("Имя обновлено ✅", keyboard=edit_keyboard)
        else:
            u["step"] = "gender"
            ctx.reply("Выберите пол:", keyboard=gender_keyboard)
        return

    # -------- День рождения --------
    if step == "birth_day":
        if not text.isdigit() or not 1 <= int(text) <= 31:
            ctx.reply("Введите число от 1 до 31")
            return
        u["birth_day"] = int(text)
        u["step"] = "birth_month"
        ctx.reply("Введите месяц рождения (1–12):")
        return

    if step == "birth_month":
        if not text.isdigit() or not 1 <= int(text) <= 12:
            ctx.reply("Введите число от 1 до 12")
            return
        u["birth_month"] = int(text)
        u["step"] = "birth_year"
        ctx.reply("Введите год рождения:")
        return

    if step == "birth_year":
        if not text.isdigit():
            ctx.reply("Введите год числом")
            return
        year = int(text)
        try:
            birthdate = datetime(year, u["birth_month"], u["birth_day"])
        except ValueError:
            ctx.reply("Некорректная дата, попробуйте снова")
            u["step"] = "birth_day"
            return

        age = datetime.now().year - year - ((datetime.now().month, datetime.now().day) < (u["birth_month"], u["birth_day"]))
        if age < 18:
            ctx.reply("Доступ запрещён, возраст < 18 лет 🚫")
            u["step"] = None
            return

        u["birthdate"] = birthdate.strftime("%d.%m.%Y")
        u["age"] = age
        u["zodiac"] = get_zodiac(u["birth_day"], u["birth_month"])  # Используется функция get_zodiac

        if u.get("step_edit"):
            u["step"] = "edit"
            ctx.reply("Дата рождения обновлена ✅", keyboard=edit_keyboard)
        else:
            u["step"] = "city_search"
            u["city_mode"] = "profile_create"
            ctx.reply("Введите первые буквы города:")
        return

        
# -------- Город --------
    if step == "city_search":
        if len(text) < 2:
            ctx.reply("Введите минимум 2 символа")
            return

        send_city_selection(ctx, text)
        return



           
   

    
    
    
    
    
    # -------- Обо мне --------
    if step == "about":
        if not text:
            ctx.reply("Напишите текст о себе")
            return
        u["about"] = text
        u["step"] = "photo"
        ctx.reply("📸 Пришлите фото (вложение или ссылка):")
        return

    # -------- Фото --------
    if step == "photo":
        photo_url = None
        for att in attachments:
            if att.get("type") == "image":
                photo_url = att.get("payload", {}).get("url")
                break
        if not photo_url and text.startswith("http"):
            photo_url = text
        if not photo_url:
            ctx.reply("❌ Фото не найдено. Пришлите изображение или ссылку.")
            return

        u["photo_url"] = photo_url
        u["step"] = None  # анкета заполнена

        save_profile(chat_id, u)
        profile = get_profile(chat_id)

        emoji = "👨" if u.get("gender") == "М" else "👩"
        result = (
            f"{emoji} Ваша анкета:\n\n"
            f"Имя: {u.get('name')}\n"
            f"Пол: {u.get('gender')}\n"
            f"🎂 Дата рождения: {u.get('birthdate')}\n"
            f"🎈 Возраст: {u.get('age')}\n"
            f"🔮 Знак зодиака: {u.get('zodiac')}\n"
            f"🏙 Город: {u.get('city')}\n"
            f"✍️ О себе: {u.get('about')}\n\n"
            f"📸 Фото:\n{u.get('photo_url')}"
        )
        ctx.reply(result, keyboard=save_menu)
        return       
        

###############################################################################


    















# ================== СТАРТ ==================
@bot.on("bot_started")
def start(ctx):
    chat_id = str(ctx.chat_id)
    profile = get_profile(chat_id)
    users.setdefault(chat_id, {"step": None})
    u = users [chat_id]

    profile = get_profile(chat_id)
    if profile:
        if profile.get("deleted_at"):
            ctx.reply("⚠️ Ваша анкета помечена на удаление. Восстановить?", keyboard=restore_keyboard)
            return
        else:
            ctx.reply("Главное меню:", keyboard=main_menu(profile))
            return
    else:
        ctx.reply("🔞 Вам есть 18 лет?", keyboard=age_keyboard)









# Обработчик колбэков
# Обработчик колбэков
# Обработчик колбэков
# Обработчик колбэков
@bot.on("message_callback")
def handle_callback(ctx):
    chat_id = str(ctx.chat_id)
    global users  # Обращаемся к глобальному слою users

    # Если пользователя нет в списке, добавляем пустой объект
    if chat_id not in users:
        users[chat_id] = {}

    # Получаем объект пользователя
    u = users[chat_id]

    # Обрабатываем колбэки
    if ctx.payload == "vip_30":
        tariff_price = 300
        link = intellectmoney_link(
            order_id=str(chat_id),
            amount=tariff_price,
            client_email="email@address.com"  # тут можно динамически подставлять email пользователя
        )
        reply_text = f"Вы выбрали тариф \"VIP 30 дней\" стоимостью {tariff_price} рублей."
        reply_keyboard = InlineKeyboard(
            [{"text": "💳 Оплатить", "url": link}],
            [{"text": "Отмена", "callback": "back"}]
        )
        ctx.reply(reply_text, keyboard=reply_keyboard)

    elif ctx.payload == "vip_180":
        tariff_price = 1500
        order_id = f"{chat_id}_{int(time.time())}"
        client_email = "email@address.com"  # сюда можешь подставить реальный email
        link = intellectmoney_link(
            order_id=order_id,
            amount=tariff_price,
            client_email=client_email
        )
        reply_text = f'Вы выбрали тариф "VIP 6 месяцев" стоимостью {tariff_price} рублей.'
        reply_keyboard = InlineKeyboard(
            [{"text": "💳 Оплатить", "url": link}],
            [{"text": "Отмена", "callback": "back"}]
        )
        ctx.reply(reply_text, keyboard=reply_keyboard)


    elif ctx.payload == "vip_365":
        tariff_price = 2500
        order_id = f"{chat_id}_{int(time.time())}"
        client_email = "email@address.com"
        link = intellectmoney_link(
            order_id=order_id,
            amount=tariff_price,
            client_email=client_email
        )
        reply_text = f'Вы выбрали тариф "VIP 12 месяцев" стоимостью {tariff_price} рублей.'
        reply_keyboard = InlineKeyboard(
            [{"text": "💳 Оплатить", "url": link}],
            [{"text": "Отмена", "callback": "back"}]
        )
        ctx.reply(reply_text, keyboard=reply_keyboard)

    elif ctx.payload == "start_buh":
        subprocess.Popen(["python", "buh.py"])
        ctx.reply("✅ BUH запущен!")

    elif ctx.payload == "stop_buh":
        subprocess.Popen(["taskkill", "/F", "/IM", "python.exe"])
        ctx.reply("⛔ BUH остановлен!")

    elif ctx.payload == "open_profile":
        # Показываем профиль пользователя
        profile = get_profile(chat_id)
        if not profile:
            ctx.reply("Анкета не найдена")
            return
        show_profile(ctx, profile, profile_menu)
    elif ctx.payload == "admin_panel":
        # Показываем админ панель
        if str(ctx.chat_id) != str(ADMIN_ID):
            ctx.reply("⛔ Доступ запрещён")
            return
        admin(ctx)
    elif ctx.payload == "open_filters":
        # Открытие фильтров
        show_filters(ctx)
    elif ctx.payload == "gender_filters":
        # Выбор пола
        ctx.reply("Выберите пол для фильтров:", keyboard=gender_filters)
    elif ctx.payload == "age_filters":
        # Выбор возраста
        profile = get_profile(chat_id) or {}
        min_age = profile.get("filters_age_min", MIN_AGE_LIMIT)
        max_age = profile.get("filters_age_max", MAX_AGE_LIMIT)
        ctx.reply("Выберите возраст для фильтров:", keyboard=age_keyboard_filters(min_age, max_age))
    elif ctx.payload == "city_filters":
        # Выбор города фильтр
        u["step"] = "city_search"
        u["city_mode"] = "filters"
        ctx.reply("Введите первые буквы города для фильтра:")
    elif ctx.payload == "done_filters":
        # Завершаем установку фильтров
        ctx.reply("Фильтры сохранены ✅", keyboard=main_menu(get_profile(chat_id)))
    elif ctx.payload in ("gender_filter_m", "gender_filter_f", "gender_filter_any"):
        # Устанавливаем фильтр по полу
        value = {
            "gender_filter_m": "М",
            "gender_filter_f": "Ж",
            "gender_filter_any": "Любой"
        }[ctx.payload]
        update_filter(chat_id, "filters_gender", value)
        profile = get_profile(chat_id) or {}
        ctx.reply("⚙️ Ваши фильтры:", keyboard=keyboard_filters(profile))
    elif ctx.payload in (
        "age_min_minus", "age_min_plus",
        "age_max_minus", "age_max_plus"
    ):
        # Обновляем диапазон возрастов
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
        ctx.reply("Выберите возраст для фильтров:", keyboard=age_keyboard_filters(min_age, max_age))
    elif ctx.payload.startswith("profile_city:"):
        # Пользователь выбрал город
        _, city_data = ctx.payload.split(":", 1)
        city, region = city_data.split("|")
        u["city"] = city
        u["region"] = region
        u["step"] = "about"
        ctx.reply(f"🏙 Город выбран: {city} ({region}).\nРасскажите немного о себе:")
    elif ctx.payload == "age_yes":
        # Пользователь подтвердил возраст
        u["step"] = "name"
        ctx.reply("Введите ваше имя:")
    elif ctx.payload == "age_no":
        # Пользователь не достиг 18 лет
        ctx.reply("Вы недостаточно взрослые для участия. До свидания!")
    elif ctx.payload == "gender_m":
        # Пользователь выбрал мужской пол
        u["gender"] = "М"
        u["step"] = "birth_day"
        ctx.reply("Введите день рождения (1–31):")
    elif ctx.payload == "gender_f":
        # Пользователь выбрал женский пол
        u["gender"] = "Ж"
        u["step"] = "birth_day"
        ctx.reply("Введите день рождения (1–31):")
    elif ctx.payload.startswith("city_selected:"):
        # === ВЫБОР ГОРОДА ===
        _, city_data = ctx.payload.split(":", 1)
        city, region = city_data.split("|")

        mode = u.get("city_mode")

        # === СОЗДАНИЕ АНКЕТЫ ===
        if mode == "profile_create":
            u["city"] = city
            u["region"] = region
            u["step"] = "about"
            u["city_mode"] = None

            ctx.reply(
                f"🏙 Город выбран: {city} ({region})\n\n"
                "Расскажите немного о себе:"
            )
            return

        # === РЕДАКТИРОВАНИЕ ПРОФИЛЯ ===
        if mode == "profile_edit":
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE profiles SET city=?, region=? WHERE user_id=?",
                (city, region, chat_id)
            )
            conn.commit()
            conn.close()

            u["city_mode"] = None
            ctx.reply(f"🏙 Город обновлён: {city} ({region})", keyboard=edit_keyboard)
            return

        # === ФИЛЬТРЫ ===
        if mode == "filters":
            update_filter(chat_id, "filters_city", city)
            update_filter(chat_id, "filters_region", region)

            u["city_mode"] = None
            u["step"] = None

            ctx.reply(
                f"🏙 Фильтр города установлен: {city}",
                keyboard=keyboard_filters(get_profile(chat_id))
            )
            return





    elif ctx.payload == "edit_city":
        # Редактирование города
        u["step"] = "city_search"
        u["city_mode"] = "profile_edit"
        ctx.reply("Введите первые буквы нового города:")

   


    elif ctx.payload == "delete":
        # Пользователь хочет удалить профиль
        ctx.reply("Вы уверены, что хотите удалить анкету?", keyboard=delete_confirm_keyboard)
    elif ctx.payload == "edit":
        # Пользователь хочет редактировать профиль
        ctx.reply("Редактирование профиля:", keyboard=edit_keyboard)
    elif ctx.payload == "save":
        # Пользователь сохраняет профиль
        save_profile(chat_id, u)
        ctx.reply("Профиль успешно сохранён!", keyboard=main_menu(get_profile(chat_id)))
    
    
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
        # Пользователь отменяет удаление профиля
        ctx.reply("Удаление отменено.", keyboard=main_menu(get_profile(chat_id)))
    elif ctx.payload == "vip":
        # Пользователь выбрал просмотр VIP
        ctx.reply(VIP_TEXT, keyboard=vip_start_keyboard)
    elif ctx.payload == "show_offer":
        # Пользователь запрашивает оферту
        ctx.reply(OFFER_TEXT, keyboard=vip_offer_keyboard)
    elif ctx.payload == "offer_accept":
        # Пользователь согласился с офертой
        ctx.reply("💎 Выбирайте тариф для подписки", keyboard=vip_keyboard)
    elif ctx.payload == "offer_decline":
        # Пользователь отказался от оферты
        profile = get_profile(str(ctx.chat_id))
        ctx.reply(
            "❌ Вы не приняли условия оферты.\n\n"
            "VIP-функции недоступны.",
            keyboard=main_menu(profile)
        )
    elif ctx.payload == "back":
        # Пользователь вернулся назад
        u["step"] = None
        ctx.reply("Главное меню:", keyboard=main_menu(get_profile(chat_id)))
    elif ctx.payload == "edit_name":
        # Редактирование имени
        u["step"] = "edit_name"
        ctx.reply("Введите новое имя:")
    elif ctx.payload == "edit_gender":
        # Редактирование пола
        u["step"] = "edit_gender"
        ctx.reply("Выберите новый пол:", keyboard=gender_keyboard)
    elif ctx.payload == "edit_birthdate":
        # Редактирование даты рождения
        u["step"] = "edit_birthdate"
        ctx.reply("Введите день рождения (1–31):")
    elif ctx.payload == "edit_photo":
        # Редактирование фотографии
        u["step"] = "edit_photo"
        ctx.reply("Загрузите новое фото (пришлите вложением или ссылкой):")
    elif ctx.payload == "edit_about":
        # Редактирование информации о себе
        u["step"] = "edit_about"
        ctx.reply("Расскажите немного о себе:")
    elif ctx.payload == "edit_done":
        # Сохранение изменений в профиле
        save_profile(chat_id, u)
        ctx.reply("Изменения сохранены!", keyboard=main_menu(get_profile(chat_id)))
    elif ctx.payload == "back_to_menu":
        # Возвращение в главное меню
        u["step"] = None
        ctx.reply("Главное меню:", keyboard=main_menu(get_profile(chat_id)))
    elif ctx.payload == "edit_profile":
        # Переход в режим редактирования профиля
        ctx.reply("Что вы хотите изменить?", keyboard=edit_keyboard)


    elif ctx.payload == "ruletka":
        # Запуск чата-рулетки
        ctx.reply(
            "💬 Чат-рулетка готова. Выберите действие:",
            keyboard=ruletka_keyboard
        )




    elif ctx.payload == "vip_tariv":
        # Просмотр тарифов VIP
        ctx.reply("💎 Выберите тариф для подписки", keyboard=vip_keyboard)
    
    
    
    elif ctx.payload == "restore_profile":
        profile = get_profile(chat_id)
        if profile.get("deleted_at"):
            # Снимаем пометку удаления
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE profiles SET deleted_at=NULL WHERE user_id=?", (chat_id,))
            conn.commit()
            conn.close()

            ctx.reply("♻ Ваша анкета восстановлена!", keyboard=main_menu(profile))
        else:
            ctx.reply("Анкета не была удалена или уже восстановлена.", keyboard=main_menu(profile))


    elif ctx.payload == "cancel_restore":
        # Пользователь отказался восстановить
        ctx.reply("❌ Анкета не восстановлена.", keyboard=restore_keyboard)

    
    
    
    
    elif ctx.payload == "roulette":
        # Рулетка
        roulette(ctx)


    elif ctx.payload == "leave_chat":
        user_id = chat_id

        if user_id not in active_chats:
            ctx.reply("❌ Вы не в чате")
            return

        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)

        # Убираем из очереди
        if user_id in queue:
            queue.remove(user_id)
        if partner_id in queue:
            queue.remove(partner_id)

        ctx.reply(
            "⏹ Вы вышли из чата",
            keyboard=ruletka_keyboard
        )

        if partner_id in contexts:
            contexts[partner_id].reply(
                "❗ Собеседник вышел из чата",
                keyboard=ruletka_keyboard
            )

        return


    else:
        print("Необработанный колбэк:", ctx.payload)
		
		

        
        
        




# ================== РУЛЕТКА ==================
# ================== РУЛЕТКА ==================
@bot.command("roulette")
def roulette(ctx):
    user_id = str(ctx.chat_id)
    contexts[user_id] = ctx

    # Уже в чате
    if user_id in active_chats:
        ctx.reply("❗ Вы уже в чате")
        return

    # Уже в очереди
    if user_id in queue:
        ctx.reply("⏳ Вы уже в очереди")
        return

    # === ЕСЛИ В ОЧЕРЕДИ КТО-ТО ЕСТЬ ===
    if queue:
        partner_id = queue.pop(0)

        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id

        # фиксируем время начала чата
        now = time.time()
        chat_started_at[user_id] = now
        chat_started_at[partner_id] = now

        # таймер 3 минуты (если оба не VIP)
        threading.Thread(
            target=chat_timer,
            args=(user_id, partner_id),
            daemon=True
        ).start()

        log.info(f"[Connect] {user_id} ↔ {partner_id}")

        # Сообщения о соединении
        ctx.reply("✨ Собеседник найден! Начните общение 👋")
        if partner_id in contexts:
            contexts[partner_id].reply("✨ Собеседник найден! Начните общение 👋")

        # Получаем профили
        user_profile = get_profile(user_id)
        partner_profile = get_profile(partner_id)

        def get_emoji(profile):
            if not profile:
                return "👤"
            if profile.get("gender") == "М":
                return "👨"
            if profile.get("gender") == "Ж":
                return "👩"
            return "👤"

        leave_keyboard = InlineKeyboard(
            [{"text": "⏹ Выйти из чата", "callback": "leave_chat"}]
        )

        # Анкета партнёра
        if partner_profile:
            ctx.reply(
                f"{get_emoji(partner_profile)} Анкета собеседника:\n\n"
                f"Имя: {partner_profile.get('name')}\n"
                f"Пол: {partner_profile.get('gender')}\n"
                f"🎂 Дата рождения: {partner_profile.get('birthdate')}\n"
                f"🎈 Возраст: {partner_profile.get('age')}\n"
                f"🏙 Город: {partner_profile.get('city')}\n"
                f"✍️ О себе: {partner_profile.get('about')}\n"
                f"💎 VIP: {'да' if partner_profile.get('is_vip') else 'нет'}\n"
                f"📸 Фото:\n{partner_profile.get('photo_url')}",
                keyboard=leave_keyboard
            )

        # Анкета пользователя партнёру
        if user_profile and partner_id in contexts:
            contexts[partner_id].reply(
                f"{get_emoji(user_profile)} Анкета собеседника:\n\n"
                f"Имя: {user_profile.get('name')}\n"
                f"Пол: {user_profile.get('gender')}\n"
                f"🎂 Дата рождения: {user_profile.get('birthdate')}\n"
                f"🎈 Возраст: {user_profile.get('age')}\n"
                f"🏙 Город: {user_profile.get('city')}\n"
                f"✍️ О себе: {user_profile.get('about')}\n"
                f"💎 VIP: {'да' if user_profile.get('is_vip') else 'нет'}\n"
                f"📸 Фото:\n{user_profile.get('photo_url')}",
                keyboard=leave_keyboard
            )

    # === ЕСЛИ ОЧЕРЕДЬ ПУСТА ===
    else:
        queue.append(user_id)
        log.info(f"[Queue] {user_id}")
        ctx.reply("🔎 Ищем собеседника...")




@bot.command("leave")
def leave_chat(ctx):
    user_id = str(ctx.chat_id)
    if user_id not in active_chats:
        ctx.reply("❌ Вы не в чате")
        return
    partner_id = active_chats.pop(user_id)
    active_chats.pop(partner_id, None)
    ctx.reply("❌ Вы вышли из чата")
    if partner_id in contexts:
        contexts[partner_id].reply("❗ Собеседник вышел из чата")
		

# ================== АДМИН ПАНЕЛЬ ==================








# ================== Админ команда ==================
@bot.command("admin")
def admin(ctx):
    if str(ctx.chat_id) != str(ADMIN_ID):
        ctx.reply("⛔ Доступ запрещён")
        return

    stats = get_stats()

    text = (
        "📊 *Админ-панель*\n\n"
        "👥 Пользователи:\n"
        f"• Всего: {stats['users_total']}\n"
        f"• Мужчин: {stats['users_m']}\n"
        f"• Женщин: {stats['users_f']}\n\n"
        "💎 VIP подписка:\n"
        f"• Всего VIP: {stats['vip_total']}\n"
        f"• Мужчин VIP: {stats['vip_m']}\n"
        f"• Женщин VIP: {stats['vip_f']}"
    )

    # ------------------ Кнопки ------------------


    # Создаем кнопки
    keyboard = InlineKeyboard(
        [{"text": "▶️ Запустить BUH", "callback": "start_buh"}],
        [{"text": "⏹ Остановить BUH", "callback": "stop_buh"}]
    )

    # Отправляем сообщение с клавиатурой
    ctx.reply(text, keyboard=keyboard)



# ================== Функция статистики ==================
def get_stats():
    now = datetime.now().timestamp()
    stats = {}

    conn = sqlite3.connect(DB_FILE)  # Укажи путь к своей базе
    cursor = conn.cursor()

    # ---------- Пользователи ----------
    cursor.execute("SELECT COUNT(*) FROM profiles")
    stats["users_total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM profiles WHERE gender='М'")
    stats["users_m"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM profiles WHERE gender='Ж'")
    stats["users_f"] = cursor.fetchone()[0]

    # ---------- VIP ----------
    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE vip_until IS NOT NULL AND vip_until > ?",
        (now,)
    )
    stats["vip_total"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE gender='М' AND vip_until > ?",
        (now,)
    )
    stats["vip_m"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM profiles WHERE gender='Ж' AND vip_until > ?",
        (now,)
    )
    stats["vip_f"] = cursor.fetchone()[0]

    conn.close()
    return stats




# ====== Функции для buh.py ======
def start_buh(ctx):
    global buh_process
    if buh_process and buh_process.poll() is None:
        ctx.reply("⚠️ buh.py уже запущен")
        return
    buh_process = subprocess.Popen([sys.executable, "buh.py"])
    ctx.reply("✅ buh.py запущен")

def stop_buh(ctx):
    global buh_process
    if not buh_process or buh_process.poll() is not None:
        ctx.reply("⚠️ buh.py не запущен")
        return
    buh_process.terminate()
    buh_process.wait()
    buh_process = None
    ctx.reply("✅ buh.py остановлен")









# Главная функция старта
if __name__ == "__main__":
    log.info("🚀 Bot started")
    create_db()  # создаем таблицу, если её нет
    delete_expired_profiles()
    bot.run()