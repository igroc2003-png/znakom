import logging
from datetime import datetime
from maxgram import Bot
from maxgram.keyboards import InlineKeyboard
from .db import save_profile, delete_profile, find_cities, get_zodiac
from . import profile

# ================== ЛОГИ ==================
logging.basicConfig(
    filename="anketa.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.info("🚀 Anketa загружена")

# ================== ВРЕМЕННОЕ ХРАНЕНИЕ ==================
users = {}
bot = None

# ================== КЛАВИАТУРЫ ==================
gender_keyboard = InlineKeyboard([
    {"text": "👨 Мужской", "callback": "gender_m"},
    {"text": "👩 Женский", "callback": "gender_f"}
])

save_menu = InlineKeyboard([
    {"text": "💾 Сохранить ✅", "callback": "save"},
    {"text": "✏️ Редактировать", "callback": "edit"},
    {"text": "🗑 Удалить", "callback": "delete"}
])

# ================== СТАРТ АНКЕТЫ ==================
def start_anketa(ctx):
    chat_id = str(ctx.chat_id)
    users[chat_id] = {"step": "name"}
    ctx.reply("Привет 👋\nВведите ваше имя:")

# ================== CALLBACK-КНОПКИ ==================
def callbacks(ctx):
    chat_id = str(ctx.chat_id)
    payload = ctx.payload

    if chat_id not in users:
        return

    u = users[chat_id]

    if payload in ("gender_m", "gender_f"):
        u["gender"] = "М" if payload == "gender_m" else "Ж"
        u["step"] = "birth_day"
        ctx.reply("Введите день рождения (1–31):")

    elif payload == "delete":
        delete_profile(chat_id)
        users.pop(chat_id, None)

        from handlers.profile import show_menu

        ctx.reply("🗑 Анкета удалена")
        show_menu(ctx)


    elif payload == "edit":
        start_anketa(ctx)

    elif payload == "save":
        # Анкета уже сохранена ДО этого места

        ctx.reply("✅ Анкета сохранена")

        # 👉 Возвращаем в главное меню
        from handlers.profile import main_menu
        from handlers.db import get_profile

        profile = get_profile(str(ctx.chat_id))

        ctx.reply(
            "Выбери действие 👇",
            keyboard=main_menu(profile)
        )


    elif payload.startswith("city:"):
        city = payload.split("city:", 1)[1]
        u["city"] = city
        u["step"] = "about"
        ctx.reply("Расскажите о себе:")

# ================== ШАГИ АНКЕТЫ ==================
def steps(ctx):
    chat_id = str(ctx.chat_id)
    msg = ctx.message

    if chat_id not in users or not msg:
        return

    text = msg.get("body", {}).get("text", "").strip()
    attachments = msg.get("body", {}).get("attachments", [])
    step = users[chat_id]["step"]
    u = users[chat_id]

    # -------- Имя --------
    if step == "name":
        if not text:
            ctx.reply("Введите имя текстом")
            return
        u["name"] = text
        u["step"] = "gender"
        ctx.reply("Выберите пол:", keyboard=gender_keyboard)

    # -------- День --------
    elif step == "birth_day":
        if not text.isdigit() or not 1 <= int(text) <= 31:
            ctx.reply("Введите число от 1 до 31")
            return
        u["birth_day"] = int(text)
        u["step"] = "birth_month"
        ctx.reply("Введите месяц (1–12):")

    # -------- Месяц --------
    elif step == "birth_month":
        if not text.isdigit() or not 1 <= int(text) <= 12:
            ctx.reply("Введите число от 1 до 12")
            return
        u["birth_month"] = int(text)
        u["step"] = "birth_year"
        ctx.reply("Введите год рождения:")

    # -------- Год --------
    elif step == "birth_year":
        if not text.isdigit():
            ctx.reply("Введите год числом")
            return

        d, m, y = u["birth_day"], u["birth_month"], int(text)

        try:
            birthdate = datetime(y, m, d)
        except ValueError:
            ctx.reply("Некорректная дата, попробуйте снова")
            u["step"] = "birth_day"
            return

        now = datetime.now()
        u["birthdate"] = birthdate.strftime("%d.%m.%Y")
        u["age"] = now.year - y - ((now.month, now.day) < (m, d))
        u["zodiac"] = get_zodiac(d, m)

        u["step"] = "city"
        ctx.reply("Введите первые буквы города:")

    # -------- Город --------
    elif step == "city":
        cities = find_cities(text)
        if not cities:
            ctx.reply("Города не найдены, попробуйте ещё")
            return
        keyboard = InlineKeyboard(*[
            [{"text": c, "callback": f"city:{c}"}] for c in cities
        ])
        ctx.reply("Выберите город:", keyboard=keyboard)

    # -------- Обо мне --------
    elif step == "about":
        if not text:
            ctx.reply("Напишите текст о себе")
            return
        u["about"] = text
        u["step"] = "photo"
        ctx.reply("📸 Пришлите фото (вложением или ссылкой):")

    # -------- Фото --------
    elif step == "photo":
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
        u["step"] = "done"

        save_profile(chat_id, u)

        emoji = "👨" if u["gender"] == "М" else "👩"

        result = (
            f"{emoji} Ваша анкета:\n\n"
            f"Имя: {u['name']}\n"
            f"Пол: {u['gender']}\n"
            f"🎂 Дата рождения: {u['birthdate']}\n"
            f"🎈 Возраст: {u['age']}\n"
            f"🔮 Знак зодиака: {u['zodiac']}\n"
            f"🏙 Город: {u['city']}\n"
            f"✍️ Обо мне: {u['about']}\n\n"
            f"📸 Фото:\n{u['photo_url']}"
        )

        ctx.reply(result, keyboard=save_menu)

# ================== РЕГИСТРАЦИЯ ==================
def register_anketa_handlers(bot_instance: Bot):
    global bot
    bot = bot_instance
    bot.on("message_callback")(callbacks)
    bot.on("message_created")(steps)
    logging.info("✅ anketa handlers зарегистрированы")
