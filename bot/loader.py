import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN, LOG_FILE

# 👇 ИСПРАВЛЕНИЕ: Импортируем DefaultBotProperties оттуда же, откуда и Bot
# Это работает на всех версиях 3.7+
from aiogram.client.bot import DefaultBotProperties 

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
# Используем новый синтаксис
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=storage)

# Временная память (RAM)
user_settings = {}
search_cache = {}
error_cache = {}