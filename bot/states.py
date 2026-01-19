from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    waiting_for_nickname = State()

class Playlist(StatesGroup):
    waiting_for_title = State()
    waiting_for_rename = State() # Новое!

class Support(StatesGroup):
    waiting_for_message = State()