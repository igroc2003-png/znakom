
from aiogram.fsm.state import StatesGroup, State

class Profile(StatesGroup):
    name = State()
    age = State()
    gender = State()
    city = State()
    about = State()

class Filters(StatesGroup):
    min_age = State()
    max_age = State()
    city = State()
