import asyncio
import sys
import subprocess
from loader import dp, bot, logger
import handlers # ОБЯЗАТЕЛЬНО ИМПОРТИРУЕМ, ЧТОБЫ РАБОТАЛО

# Обновление
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
except: pass

if __name__ == "__main__":
    try:
        logger.info("Bot Started!")
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        logger.info("Bot Stopped")