from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_genres = State()

class Playlist(StatesGroup):
    waiting_for_title = State()
    waiting_for_rename = State()

class Support(StatesGroup):
    waiting_for_message = State()

class Broadcast(StatesGroup):
    waiting_for_content = State()
    waiting_for_button = State() # Новое: кнопка для рассылки
    waiting_for_confirm = State()

class AdminActions(StatesGroup):
    waiting_for_user_id = State() # Поиск юзера