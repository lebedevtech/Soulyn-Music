import sys
import os
import asyncio
import logging

# --- ПРОВЕРКА ОКРУЖЕНИЯ ---
try:
    from dotenv import load_dotenv
except ImportError:
    print("\n❌ ОШИБКА: Библиотеки не найдены!")
    print("Похоже, вы запустили бота не через виртуальное окружение.")
    print("👉 Используйте команду: .\\venv\\Scripts\\python run.py\n")
    sys.exit(1)

# --- ИМПОРТЫ БОТА ---
try:
    from bot.loader import dp, bot as telegram_bot, logger
    import bot.handlers
    from bot.database import Database
except ImportError as e:
    print(f"\n❌ ОШИБКА ИМПОРТА: {e}")
    print("Проверьте, что файл .env создан и библиотека python-dotenv установлена.\n")
    sys.exit(1)

async def main():
    logger.info("🚀 Starting Soulyn Music Bot...")

    # 👇 ИСПРАВЛЕНИЕ: Убрали await, так как функция синхронная
    Database.migrate_db()

    # Удаляем вебхуки (очистка очереди старых апдейтов)
    await telegram_bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг (бесконечный цикл прослушивания)
    logger.info("Bot is ready and listening!")
    await dp.start_polling(telegram_bot)

if __name__ == "__main__":
    # Настройка для Windows (обязательно для aiogram 3+ на винде)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Bot stopped manually!")
    except Exception as e:
        logger.critical(f"Bot crashed with error: {e}")