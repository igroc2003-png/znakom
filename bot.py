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
# Используем show_menu(ctx), чтобы main_menu сама выбирала правильный вид клавиатуры
@bot.command("start")
def start(ctx):
    profile.show_menu(ctx)

# ================== ЗАПУСК БОТА ==================
logging.info("🚀 Запуск бота")
bot.run()


