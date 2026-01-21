import asyncio
import logging
import sys
import os
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from bot.config import ADMIN_ID
from bot.database import Database

# 1. НАСТРОЙКА ПУТЕЙ И OKРУЖЕНИЯ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
if os.path.exists(BIN_DIR):
    os.environ["PATH"] += os.pathsep + BIN_DIR

# 2. СОЗДАНИЕ ВАЖНЫХ ПАПОК
if not os.path.exists("downloads"): os.makedirs("downloads")
if not os.path.exists("data"): os.makedirs("data")

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

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
    print("⏳ Импортируем библиотеки...")
    try:
        from bot.loader import bot as tg_bot, dp
        import bot.handlers  
        
        # 🔥 Инициализируем БД
        print("🗄 Подключаем базу данных...")
        await Database.init_db()
        print("✅ Библиотеки успешно загружены!")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        raise e

    await set_bot_commands(tg_bot)

    print("🚀 Запускаем бота...")
    try:
        await tg_bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(tg_bot)
    except Exception as e:
        print(f"❌ ОШИБКА ЗАПУСКА: {e}")
    finally:
        await tg_bot.session.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())