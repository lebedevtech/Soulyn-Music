import asyncio
from aiogram import Bot, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from bot.config import BOT_TOKEN
from bot.database import Database

# Тексты на всех 6 языках бота
MESSAGES = {
    'ru': (
        "👋 <b>Ваш Music Genie на связи!</b>\n\n"
        "У нас произошел <b>ребрендинг</b>. Мы расширяемся и превращаемся в целую <b>экосистему</b> для твоей музыки. "
        "Это обновление сделает сервис быстрее и качественнее.\n\n"
        "✅ <b>Всё на месте:</b> Все твои треки и плейлисты сохранены и уже ждут тебя в обновленной версии!\n\n"
        "Нажми кнопку ниже, чтобы продолжить слушать 👇"
    ),
    'en': (
        "👋 <b>Your Music Genie is here!</b>\n\n"
        "We've undergone a <b>rebranding</b>. We are expanding into a complete <b>ecosystem</b> for your music. "
        "This update is a step to become faster and better.\n\n"
        "✅ <b>Everything is safe:</b> All your tracks and playlists are saved and waiting for you in the updated version!\n\n"
        "Click the button below to continue listening 👇"
    ),
    'ua': (
        "👋 <b>Ваш Music Genie на зв'язку!</b>\n\n"
        "У нас відбувся <b>ребрендинг</b>. Ми розширюємось і перетворюємось на цілу <b>екосистему</b> для твоєї музики. "
        "Це оновлення зробить сервіс швидшим та якіснішим.\n\n"
        "✅ <b>Все на місці:</b> Всі твої треки та плейлисти збережені та вже чекають на тебе в оновленій версії!\n\n"
        "Натисни кнопку нижче, щоб продовжити 👇"
    ),
    'kz': (
        "👋 <b>Сіздің Music Genie байланыста!</b>\n\n"
        "Бізде <b>ребрендинг</b> өтті. Біз сіздің музыкаңыз үшін толық <b>экожүйеге</b> айналудамыз. "
        "Бұл жаңарту сервисті тезірек және сапалырақ етеді.\n\n"
        "✅ <b>Бәрі орнында:</b> Барлық тректеріңіз бен плейлисттеріңіз сақталды және жаңартылған нұсқада сізді күтуде!\n\n"
        "Тыңдауды жалғастыру үшін төмендегі түймені басыңыз 👇"
    ),
    'uz': (
        "👋 <b>Sizning Music Genie aloqada!</b>\n\n"
        "Bizda <b>rebranding</b> bo'lib o'tdi. Biz musiqangiz uchun to'liq <b>ekotizimga</b> aylanmoqdamiz. "
        "Ushbu yangilanish xizmatni tezroq va sifatliroq qiladi.\n\n"
        "✅ <b>Hammasi joyida:</b> Barcha treklaringiz va pleylistlaringiz saqlangan va yangilangan versiyada sizni kutmoqda!\n\n"
        "Eshitishda davom etish uchun pastdagi tugmani bosing 👇"
    ),
    'ar': (
        "👋 <b>مساعدك Music Genie معك!</b>\n\n"
        "لقد قمنا بـ <b>تغيير علامتنا التجارية</b>. نحن نتوسع لنتحول إلى <b>نظام بيئي</b> متكامل لموسيقاك. "
        "هذا التحديث سيجعل الخدمة أسرع وأفضل.\n\n"
        "✅ <b>كل شيء آمن:</b> تم حفظ جميع مقاطعك وقوائم التشغيل الخاصة بك وهي بانتظارك في النسخة الجديدة!\n\n"
        "انقر على الزر أدناه للمتابعة 👇"
    )
}

BUTTON_TEXTS = {
    'ru': "🚀 Открыть Music Genie",
    'en': "🚀 Open Music Genie",
    'ua': "🚀 Відкрити Music Genie",
    'kz': "🚀 Music Genie ашу",
    'uz': "🚀 Music Genie-ni ochish",
    'ar': "🚀 افتح Music Genie"
}

async def start_migration():
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}?start=migrated"

    users_dict, _ = Database.get_stats()
    print(f"🚀 Начинаю рассылку для {len(users_dict)} пользователей...")

    count = 0
    for uid_str, user_data in users_dict.items():
        uid = int(uid_str)
        lang = user_data.get('lang', 'ru')
        if lang not in MESSAGES: lang = 'ru'
        
        kb = InlineKeyboardBuilder()
        kb.button(text=BUTTON_TEXTS[lang], url=bot_link)
        
        try:
            await bot.send_message(uid, MESSAGES[lang], reply_markup=kb.as_markup())
            count += 1
            if count % 10 == 0: print(f"✅ Отправлено {count} сообщений...")
            await asyncio.sleep(0.05) 
        except Exception:
            pass

    print(f"\n✨ Готово! Сообщение получили {count} человек.")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(start_migration())