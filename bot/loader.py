import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties 
from bot.config import BOT_TOKEN, LOG_FILE

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MusicGenie")

# Инициализация хранилища
storage = MemoryStorage()

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=storage)

# --- ОПТИМИЗАЦИЯ: Временная память (RAM) ---
# user_settings: {user_id: {'lang': 'ru', 'status': 'user', ...}}
# Загружается при старте из БД, чтобы не дёргать базу ради простых проверок (язык, лимиты)
user_settings = {}

# search_cache: Кэш результатов поиска YouTube/iTunes
search_cache = {}

# error_cache: Лог последних ошибок юзеров
error_cache = {}