
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
import aiosqlite

from states import Profile, Filters
from keyboards import menu
from db import DB
from config import MONETIZATION_ENABLED

router = Router()
active_chats = {}

@router.message(CommandStart())
async def start(m: Message):
    await m.answer("👋 Добро пожаловать!", reply_markup=menu())

@router.callback_query(F.data=="profile")
async def profile(c:CallbackQuery,state:FSMContext):
    await state.set_state(Profile.name)
    await c.message.answer("Имя?")
    await c.answer()

@router.message(Profile.name)
async def p_name(m:Message,state:FSMContext):
    await state.update_data(name=m.text)
    await state.set_state(Profile.age)
    await m.answer("Возраст?")

@router.message(Profile.age)
async def p_age(m:Message,state:FSMContext):
    await state.update_data(age=int(m.text))
    await state.set_state(Profile.gender)
    await m.answer("Пол?")

@router.message(Profile.gender)
async def p_gender(m:Message,state:FSMContext):
    await state.update_data(gender=m.text)
    await state.set_state(Profile.city)
    await m.answer("Город?")

@router.message(Profile.city)
async def p_city(m:Message,state:FSMContext):
    await state.update_data(city=m.text)
    await state.set_state(Profile.about)
    await m.answer("О себе")

@router.message(Profile.about)
async def p_about(m:Message,state:FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "REPLACE INTO users VALUES(?,?,?,?,?,?,?,?,?,0)",
            (m.from_user.id,d['name'],d['age'],d['gender'],d['city'],m.text,18,99,d['city'])
        )
        await db.commit()
    await state.clear()
    await m.answer("✅ Анкета сохранена", reply_markup=menu())

@router.callback_query(F.data=="filters")
async def filters(c:CallbackQuery,state:FSMContext):
    await state.set_state(Filters.min_age)
    await c.message.answer("Мин. возраст?")
    await c.answer()

@router.message(Filters.min_age)
async def fmin(m:Message,state:FSMContext):
    await state.update_data(min_age=int(m.text))
    await state.set_state(Filters.max_age)
    await m.answer("Макс. возраст?")

@router.message(Filters.max_age)
async def fmax(m:Message,state:FSMContext):
    await state.update_data(max_age=int(m.text))
    await state.set_state(Filters.city)
    await m.answer("Город или Любой")

@router.message(Filters.city)
async def fcity(m:Message,state:FSMContext):
    d = await state.get_data()
    city = None if m.text.lower()=="любой" else m.text
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE users SET min_age=?, max_age=?, city_filter=? WHERE user_id=?",
            (d['min_age'],d['max_age'],city,m.from_user.id)
        )
        await db.commit()
    await state.clear()
    await m.answer("⚙️ Фильтры сохранены", reply_markup=menu())

@router.callback_query(F.data=="roulette")
async def roulette(c:CallbackQuery):
    uid = c.from_user.id
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO queue VALUES(?)",(uid,))
        cur = await db.execute("SELECT user_id FROM queue WHERE user_id!=? LIMIT 1",(uid,))
        row = await cur.fetchone()
        if row:
            partner = row[0]
            await db.execute("DELETE FROM queue WHERE user_id IN (?,?)",(uid,partner))
            active_chats[uid]=partner
            active_chats[partner]=uid
            await c.message.answer("💬 Собеседник найден!")
        else:
            await c.message.answer("⏳ Ожидание собеседника")
        await db.commit()
    await c.answer()

@router.message()
async def relay(m:Message):
    if m.from_user.id in active_chats:
        await m.send_copy(active_chats[m.from_user.id])

@router.callback_query(F.data=="leave")
async def leave(c:CallbackQuery):
    if c.from_user.id in active_chats:
        partner = active_chats.pop(c.from_user.id)
        active_chats.pop(partner,None)
        await c.message.answer("🚪 Чат завершён")
    await c.answer()

@router.callback_query(F.data=="delete")
async def delete(c:CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM users WHERE user_id=?",(c.from_user.id,))
        await db.commit()
    await c.message.answer("🗑 Анкета удалена")
    await c.answer()

@router.callback_query(F.data=="vip")
async def vip(c:CallbackQuery):
    if MONETIZATION_ENABLED:
        await c.message.answer("⭐ VIP активируется оплатой (заглушка)")
    else:
        await c.message.answer("Монетизация отключена")
    await c.answer()
