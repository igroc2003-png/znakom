import logging
from maxgram.keyboards import InlineKeyboard
from handlers.db import get_profile, delete_profile

logging.info("🚀 profile handlers загружены")

# ================== КЛАВИАТУРЫ ==================

def main_menu(profile):
    """
    Возвращает клавиатуру главного меню.
    Если profile есть — показываем VIP, Анкету, Фильтры, Рулетку.
    Если нет — показываем кнопку Создать анкету.
    """
    if profile:
        name, gender, *_ = profile

        emoji = "👤"
        if gender == "М":
            emoji = "👨"
        elif gender == "Ж":
            emoji = "👩"

        return InlineKeyboard(
            [{"text": "⭐ VIP", "callback": "vip"}],
            [{"text": f"{emoji} Анкета", "callback": "open_profile"}],
            [{"text": "🎯 Фильтры поиска", "callback": "filters"}],
            [{"text": "🎲 Рулетка", "callback": "roulette"}],
        )

    # Если анкета нет — показываем только кнопку Создать анкету
    return InlineKeyboard([{"text": "📝 Создать анкету", "callback": "create_profile"}])


profile_menu = InlineKeyboard(
    [
        {"text": "✏️ Редактировать", "callback": "edit_profile"},
        {"text": "🗑 Удалить", "callback": "delete_profile"},
        {"text": "⬅️ Назад", "callback": "back_to_menu"},
    ]
)

delete_confirm_menu = InlineKeyboard(
    [
        {"text": "✅ Да, удалить", "callback": "confirm_delete"},
        {"text": "❌ Нет", "callback": "back_to_menu"},
    ]
)

# ================== ОТОБРАЖЕНИЕ ==================

def show_menu(ctx):
    """
    Отображает главное меню пользователю.
    """
    profile_data = get_profile(str(ctx.chat_id))
    ctx.reply(
        "👋 ❤️🔍🎲 Привет! Это Чат-рулетка знакомств 👫\n\nВыбери действие 👇",
        keyboard=main_menu(profile_data)
    )


def show_profile(ctx):
    """
    Показывает анкету пользователя.
    """
    profile = get_profile(str(ctx.chat_id))

    if not profile:
        show_menu(ctx)
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
        text += f"\n📸 Фото: {photo}"

    ctx.reply(text, keyboard=profile_menu)


# ================== HANDLERS ==================

def register_profile_handlers(bot):
    """
    Регистрирует обработчики callback'ов для профиля.
    """
    @bot.on("message_callback")
    def callbacks(ctx):
        payload = ctx.payload
        user_id = str(ctx.chat_id)

        if payload == "open_profile":
            show_profile(ctx)

        elif payload == "back_to_menu":
            show_menu(ctx)

        elif payload == "create_profile":
            from handlers.anketa import start_anketa
            start_anketa(ctx)

        elif payload == "edit_profile":
            from handlers.anketa import start_anketa
            start_anketa(ctx)

        elif payload == "delete_profile":
            ctx.reply(
                "⚠️ Ты уверен, что хочешь удалить анкету?",
                keyboard=delete_confirm_menu
            )

        elif payload == "confirm_delete":
            delete_profile(user_id)
            ctx.reply(
                "🗑 Анкета удалена",
                keyboard=main_menu(None)
            )

    logging.info("✅ profile handlers зарегистрированы")



