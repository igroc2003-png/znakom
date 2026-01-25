import logging
from maxgram.keyboards import InlineKeyboard
from handlers.db import get_profile, delete_profile

logging.info("🚀 profile handlers загружены")

# ================== КЛАВИАТУРЫ ==================

def main_menu(has_profile: bool, gender=None):
    """Главное меню с эмодзи у кнопки Анкета"""
    if has_profile:
        profile_emoji = "👤"
        if gender == "М":
            profile_emoji = "👨"
        elif gender == "Ж":
            profile_emoji = "👩"
        return InlineKeyboard(
            [{"text": "⭐ VIP", "callback": "vip"}],
            [{"text": f"{profile_emoji} Анкета", "callback": "open_profile"}],
            [{"text": "🎯 Настроить фильтры", "callback": "filters"}],
            [{"text": "🎲 Рулетка", "callback": "roulette"}],
        )
    else:
        return InlineKeyboard(
            [{"text": "📝 Создать анкету", "callback": "create_profile"}]
        )


profile_menu = InlineKeyboard(
    [
        {"text": "✏️ Редактировать", "callback": "edit_profile"},
        {"text": "🗑 Удалить", "callback": "delete_profile"},
        {"text": "⬅️ Назад", "callback": "back_to_menu"}
    ]
)

confirm_delete_menu = InlineKeyboard(
    [
        {"text": "✅ Да", "callback": "confirm_delete"},
        {"text": "❌ Нет", "callback": "cancel_delete"},
    ]
)


# ================== ОСНОВНАЯ ЛОГИКА ==================

def show_main_menu(ctx):
    """Главное меню"""
    user_id = str(ctx.chat_id)
    profile = get_profile(user_id)
    gender = profile[1] if profile else None
    ctx.reply("Главное меню:" if profile else
              "👋 ❤️🔍🎲 Привет! Это Чат-рулетка знакомств 👫\n\nВыбери действие 👇",
              keyboard=main_menu(bool(profile), gender))


def view_profile(ctx):
    """Просмотр анкеты с эмодзи по полу"""
    user_id = str(ctx.chat_id)
    profile = get_profile(user_id)
    if not profile:
        # если анкеты нет — создаем
        from handlers.anketa import start_anketa
        start_anketa(ctx)
        return

    name, gender, birthdate, age, zodiac, city, about, photo = profile
    emoji = "👤"
    if gender == "М":
        emoji = "👨"
    elif gender == "Ж":
        emoji = "👩"

    text = (
        f"{emoji} Ваша анкета:\n\n"
        f"Имя: {name}\n"
        f"Пол: {gender}\n"
        f"🎂 Дата рождения: {birthdate}\n"
        f"🎈 Возраст: {age}\n"
        f"🔮 Знак зодиака: {zodiac}\n"
        f"🏙 Город: {city}\n"
        f"✍️ О себе: {about}\n"
    )
    if photo:
        text += f"\n📸 Фото прикреплено: {photo}"

    ctx.reply(text, keyboard=profile_menu)


# ================== РЕГИСТРАЦИЯ HANDLERS ==================

def register_profile_handlers(bot):

    @bot.command("start")
    def start(ctx):
        show_main_menu(ctx)

    @bot.on("message_callback")
    def callbacks(ctx):
        payload = ctx.payload

        if payload == "open_profile":
            view_profile(ctx)

        elif payload == "back_to_menu":
            show_main_menu(ctx)

        elif payload == "create_profile":
            from handlers.anketa import start_anketa
            start_anketa(ctx)

        elif payload == "edit_profile":
            from handlers.anketa import start_anketa
            start_anketa(ctx)

        elif payload == "delete_profile":
            ctx.reply(
                "⚠️ Вы уверены, что хотите удалить анкету?",
                keyboard=confirm_delete_menu
            )

        elif payload == "confirm_delete":
            delete_profile(str(ctx.chat_id))
            ctx.reply(
                "🗑 Анкета удалена",
                keyboard=main_menu(False)
            )

        elif payload == "cancel_delete":
            profile = get_profile(str(ctx.chat_id))
            ctx.reply(
                "Удаление отменено 👌",
                keyboard=main_menu(bool(profile))
            )


    logging.info("✅ profile handlers зарегистрированы")
