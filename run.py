import asyncio
import logging
import sys
import os
import warnings

# Убираем лишние ворнинги на Windows
warnings.filterwarnings("ignore", category=DeprecationWarning)

from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from bot.config import ADMIN_ID
from bot.database import Database

# 1. НАСТРОЙКА ПУТЕЙ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
if os.path.exists(BIN_DIR):
    os.environ["PATH"] += os.pathsep + BIN_DIR

# 2. СОЗДАНИЕ ВАЖНЫХ ПАПОК
if not os.path.exists("downloads"): os.makedirs("downloads")
if not os.path.exists("data"): os.makedirs("data")

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("MusicGenie")

async def set_bot_commands(bot):
    user_commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="ticket", description="🆘 Написать в поддержку"),
        BotCommand(command="settings", description="⚙️ Настройки языка"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = user_commands + [
        BotCommand(command="admin", description="👑 Админ-панель"),
        BotCommand(command="broadcast", description="📢 Рассылка"),
    ]
    try:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID))
    except: pass

async def main():
    logger.info("🚀 Starting Soulyn Music Bot...")
    try:
        from bot.loader import bot as tg_bot, dp
        import bot.handlers  
        
        logger.info("Checking database consistency...")
        await Database.init_db()
        logger.info("✅ Database clean.")
        
        await set_bot_commands(tg_bot)
        
        logger.info("Bot is ready and listening!")
        await tg_bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(tg_bot)
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}")
        raise e
    finally:
        try:
            await tg_bot.session.close()
        except: pass

if __name__ == "__main__":
    if sys.platform == 'win32':
        # Важно для Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")