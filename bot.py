from maxgram import Bot
from maxgram.keyboards import InlineKeyboard
from config import TOKEN

bot = Bot(TOKEN)

print("🚀 MAX бот запущен (maxgram)")

# Глобальная переменная для хранения состояния пользователя
user_states = {}

# ─────────────────────
# КЛАВИАТУРА (ПРАВИЛЬНЫЙ ВЫЗОВ)
# ─────────────────────
main_keyboard = InlineKeyboard(
    [
        {"text": "📝 Создать анкету", "callback": "create"}
    ],
    [
        {"text": "👤 Моя анкета", "callback": "profile"},
        {"text": "🗑 Удалить анкету", "callback": "delete"}
    ]
)

# Клавиатура для выбора пола
gender_keyboard = InlineKeyboard(
    [
        {"text": "🚹 Мужской", "callback": "male"},
        {"text": "🚺 Женский", "callback": "female"}
    ]
)

# ─────────────────────
# КОМАНДЫ
# ─────────────────────
bot.set_my_commands({
    "start": "Запустить бота",
    "menu": "Показать меню"
})

# ─────────────────────
# /start
# ─────────────────────
@bot.command("start")
def start(context):
    context.reply(
        "👋 Привет! Это чат знакомств\n\n"
        "Выбери действие 👇",
        keyboard=main_keyboard
    )

# ─────────────────────
# /menu
# ─────────────────────
@bot.command("menu")
def menu(context):
    context.reply(
        "📋 Главное меню",
        keyboard=main_keyboard
    )

# ─────────────────────
# ОБРАБОТКА КНОПОК
# ─────────────────────
@bot.on("message_callback")
def handle_callback(context):
    button = context.payload

    if button == "create":
        # Отправляем сообщение с запросом на ввод имени
        context.reply(
            "📝 Введите ваше имя:",
        )
        # Сохраняем состояние пользователя
        user_states[context.chat_id] = "waiting_for_name"

    elif button == "profile":
        context.reply_callback(
            "👤 Твоя анкета пока пустая",
            is_current=True
        )

    elif button == "delete":
        context.reply_callback(
            "🗑 Анкета удалена (заглушка)",
            is_current=True
        )

    elif button == "male":
        context.reply_callback(
            "🚹 Пол выбран: Мужской",
            is_current=True
        )
        # Обновляем состояние пользователя
        user_states[context.chat_id]["gender"] = "male"
        user_states[context.chat_id]["state"] = "waiting_for_age"

    elif button == "female":
        context.reply_callback(
            "🚺 Пол выбран: Женский",
            is_current=True
        )
        # Обновляем состояние пользователя
        user_states[context.chat_id]["gender"] = "female"
        user_states[context.chat_id]["state"] = "waiting_for_age"

# ─────────────────────
# ОБРАБОТКА СООБЩЕНИЙ
# ─────────────────────
@bot.on("message")
def handle_message(context):
    if user_states.get(context.chat_id) == "waiting_for_name":
        name = context.message.text
        context.reply(
            f"👋 Привет, {name}! Теперь выберите ваш пол 👇",
            keyboard=gender_keyboard
        )
        # Сохраняем имя пользователя
        user_states[context.chat_id] = {"name": name}
        # Обновляем состояние пользователя
        user_states[context.chat_id]["state"] = "waiting_for_gender"

    elif user_states.get(context.chat_id) == "waiting_for_age":
        age = context.message.text
        context.reply(
            f"👶 Ваш возраст: {age}. Анкета создана (пока заглушка)."
        )
        # Сохраняем возраст пользователя
        user_states[context.chat_id]["age"] = age
        # Обновляем состояние пользователя
        user_states[context.chat_id]["state"] = "profile_created"

# ─────────────────────
# ЗАПУСК
# ─────────────────────
bot.run()
