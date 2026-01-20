"""
Пример бота с интерактивной клавиатурой для Max

Этот бот отправляет сообщение с кнопками и обрабатывает нажатия на них.
"""

from maxgram import Bot
from maxgram.keyboards import InlineKeyboard

# Инициализация бота
# Внимание! Рекомендуется через .env получать токен!
bot = Bot("f9LHodD0cOJTtjGz_nLQlHs2b6j_MMBp1Kdb6egSNRFohzFBxRrN_C3k1Q-8NCcr5xnKBfdIyhIaJRhrWmnS")

# Создание клавиатуры
main_keyboard = InlineKeyboard(
    [
        {"text": "Отправить новое сообщение", "callback": "button1"},
    ],
    [ 
        {"text": "Изменить сообщение", "callback": "button2"},
        {"text": "Показать Назад", "callback": "button3"}
    ],
    [
        {"text": "Открыть ссылку", "url": "https://pypi.org/project/maxgram/"}
    ]
)

# Обработчик события запуска бота
@bot.on("bot_started")
def on_start(context):
    context.reply(
        "Привет! Я бот с клавиатурой. Нажми на одну из кнопок ниже:",
        keyboard=main_keyboard
    )

# Отправить клавиатуру по команде '/keyboard'
@bot.command("keyboard")
def keyboard_command(context):
    context.reply(
        "Вот клавиатура. Выбери одну из опций:",
        keyboard=main_keyboard
    )

# Обработчик нажатий на кнопки
@bot.on("message_callback")
def handle_callback(context):
    
    button = context.payload
    
    if button == "button1":
        context.reply_callback("Вы отправили новое сообщение")
    elif button == "button2":
        context.reply_callback("Вы изменили текущее сообщение", is_current=True)
    elif button == "button3":
        context.reply_callback("Вы изменили текущее сообщение с новой клавиатурой", 
                          keyboard=InlineKeyboard(
                              [{"text": "Вернуться к меню", "callback": "back_to_menu"}]
                          ),
                          is_current=True)
    elif button == "back_to_menu":
        context.reply_callback(
            "Вернемся к основному меню", 
            keyboard=main_keyboard,
            is_current=True
        )

# Запуск бота
if __name__ == "__main__":
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
