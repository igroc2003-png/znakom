
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def menu(vip=False):
    kb = [
        [InlineKeyboardButton(text="📝 Анкета", callback_data="profile")],
        [InlineKeyboardButton(text="⚙️ Фильтры", callback_data="filters")],
        [InlineKeyboardButton(text="🎲 Рулетка", callback_data="roulette")],
        [InlineKeyboardButton(text="🚪 Выйти из чата", callback_data="leave")],
        [InlineKeyboardButton(text="🗑 Удалить анкету", callback_data="delete")]
    ]
    if not vip:
        kb.insert(0,[InlineKeyboardButton(text="⭐ VIP", callback_data="vip")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
