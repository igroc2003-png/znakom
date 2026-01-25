import logging
from maxgram import Bot
from config import TOKEN
from handlers import profile, anketa, db

# ================== ЛОГИ ==================
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.info("🚀 Бот запускается")

# ================== ИНИЦИАЛИЗАЦИЯ ==================
bot = Bot(TOKEN)

# ================== БАЗА ДАННЫХ ==================
db.create_database()
logging.info("✅ База данных создана / подключена")

# ================== РЕГИСТРАЦИЯ HANDLERS ==================
profile.register_profile_handlers(bot)
logging.info("✅ profile handlers зарегистрированы")

anketa.register_anketa_handlers(bot)
logging.info("✅ anketa handlers зарегистрированы")

logging.info("✅ Все handlers зарегистрированы")

# ================== СТАРТ ==================
@bot.command("start")
def start(ctx):
    from handlers.profile import main_menu
    ctx.reply(
        "👋 ❤️🔍🎲 Привет! Это Чат-рулетка знакомств 👫\n\n"
        "Выбери действие 👇",
        keyboard=main_menu(has_profile=True)  # или False, если тут не проверяешь
    )


# ================== ЗАПУСК БОТА ==================
logging.info("🚀 Запуск бота")
bot.run()
