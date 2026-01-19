import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 1. Загружаем переменные из .env
load_dotenv()

# --- ПУТИ К ФАЙЛАМ ---
# Определяем корневую папку проекта (на 2 уровня выше этого файла)
BASE_DIR = Path(__file__).resolve().parent.parent

# 👇 ИСПРАВЛЕНИЕ: assets лежит в корне (BASE_DIR), а не внутри bot
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
BIN_DIR = BASE_DIR / "bin"

# Создаем папки, если их нет (кроме assets, они должны быть)
if not DATA_DIR.exists():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# Пути к конкретным файлам
LANG_IMG_PATH = ASSETS_DIR / "lang.jpg"
BANNER_PATH = ASSETS_DIR / "banner.jpg"
LOGO_PATH = ASSETS_DIR / "logo.jpg"

DB_FILE = DATA_DIR / "music_db.json"
USERS_FILE = DATA_DIR / "users_db.json"
LOG_FILE = DATA_DIR / "bot_errors.log"

# --- СЕКРЕТНЫЕ НАСТРОЙКИ (ИЗ .ENV) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")

# Преобразуем ID в числа (int), так как из .env они приходят строками
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID", 0))
except (ValueError, TypeError):
    print("❌ ОШИБКА: Проверь ADMIN_ID и SUPPORT_GROUP_ID в файле .env (должны быть числами)")
    sys.exit(1)

# Проверка критических токенов
if not BOT_TOKEN:
    print("❌ ОШИБКА: Не найден BOT_TOKEN в файле .env")
    sys.exit(1)

# --- ПУБЛИЧНЫЕ НАСТРОЙКИ (LINKS & CONSTANTS) ---
SUPPORT_LINK = "https://t.me/MusicGenieSupport"
CHANNEL_LINK = "https://t.me/MusicGenieNews"

# --- SPOTIFY ---
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# --- ЖАНРЫ ---
GENRES_LIST = [
    "Rock", "Pop", "Hip-Hop", "Rap", "Metal", 
    "Electronic", "Lo-Fi", "Jazz", "Classical", 
    "R&B", "Indie", "K-Pop", "Phonk", "Techno",
    "Alternative", "Hard Rock", "Punk", "Dance",
    "House", "Trap", "Soundtrack", "Soul"
]

# --- СЕТЬ ---
PROXY_URL = None  
COOKIES_PATH = None 
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"