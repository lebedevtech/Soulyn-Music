import os
import asyncio
from aiogram import types, F
from aiogram.types import FSInputFile, InputMediaPhoto
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from bot.loader import dp, bot
from bot.database import Database
from bot.config import BIN_DIR 
from bot.texts import T
import bot.keyboards as kb
from bot.utils import delete_later

# Пути к картинкам
BANNER_PATH = os.path.join("bot", "assets", "banner.jpg")
if not os.path.exists(BANNER_PATH): BANNER_PATH = "assets/banner.jpg"

LANG_IMG_PATH = os.path.join("bot", "assets", "lang.png")
if not os.path.exists(LANG_IMG_PATH): LANG_IMG_PATH = "assets/lang.png"


# --- START ---
@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    
    # Регистрация (Async)
    # Аргументы для рефералки
    args = msg.text.split()[1:] if len(msg.text.split()) > 1 else []
    referrer = int(args[0]) if args and args[0].isdigit() and int(args[0]) != uid else None
    
    await Database.register_user(uid, msg.from_user.username, msg.from_user.full_name, referrer_id=referrer)
    
    # Проверяем, выбран ли язык
    user = await Database.get_user(uid)
    
    if not user.get('lang'):
        # Если языка нет — предлагаем выбор (с картинкой, как было у тебя)
        welcome_text = T(uid, 'welcome', 'Welcome! Choose language:').format(msg.from_user.first_name)
        if os.path.exists(LANG_IMG_PATH):
            await msg.answer_photo(FSInputFile(LANG_IMG_PATH), caption=welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
        else:
            await msg.answer(welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
    else:
        # Если язык есть — сразу в меню
        await open_main_menu(uid, msg.chat.id)

@dp.callback_query(F.data.startswith("lang:"))
async def set_language(clb: types.CallbackQuery):
    lang_code = clb.data.split(":")[1]
    uid = clb.from_user.id
    await Database.set_lang(uid, lang_code)
    await clb.answer(f"Language: {lang_code.upper()}")
    await clb.message.delete()
    await open_main_menu(uid, clb.message.chat.id)

# --- MENU HELPER (Восстановлена логика с баннером) ---
async def open_main_menu(uid, chat_id, clb=None, text_key='menu'):
    markup = kb.kb_menu(uid) # Теперь это синхронная функция в kb, await не нужен если там нет БД
    text = T(uid, text_key)
    
    has_banner = os.path.exists(BANNER_PATH)
    photo = FSInputFile(BANNER_PATH) if has_banner else None

    # Попытка редактирования (если вызвано кнопкой)
    if clb:
        try: await clb.answer()
        except: pass
        
        # Если это сообщение с медиа (аудио), мы не можем превратить его в фото -> удаляем
        is_media_message = clb.message.audio or clb.message.voice or clb.message.video
        if not is_media_message:
            try:
                # Если уже было фото и есть баннер -> меняем медиа
                if clb.message.photo and has_banner:
                    media = InputMediaPhoto(media=photo, caption=text, parse_mode="HTML")
                    await clb.message.edit_media(media, reply_markup=markup)
                    await Database.set_menu_id(uid, clb.message.message_id)
                    return
                # Если текста -> редактируем текст (только если баннера нет, иначе удаляем и шлем фото)
                elif not clb.message.photo and not has_banner:
                    await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
                    await Database.set_menu_id(uid, clb.message.message_id)
                    return
            except Exception as e: 
                pass 
        
        # Если не вышло отредактировать -> удаляем старое
        try: await clb.message.delete()
        except: pass

    # Удаляем старое меню из базы, чтобы не висело
    old_menu_id = await Database.get_menu_id(uid)
    if old_menu_id:
        try: await bot.delete_message(chat_id, old_menu_id)
        except: pass
    
    # Отправляем новое
    if has_banner:
        msg = await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        msg = await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
    
    await Database.set_menu_id(uid, msg.message_id)

# --- TOP CHART (Восстановлено) ---
@dp.callback_query(F.data == "view:top")
async def view_top_chart(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    
    # 🔥 Await DB
    tracks = await Database.get_top_tracks(limit=10)
    
    if not tracks:
        await clb.answer(T(uid, 'top_chart_empty', "Top chart is empty!"), show_alert=True)
        return

    text = T(uid, 'top_chart_title', "🔥 <b>Top {count} Popular Tracks:</b>").format(count=len(tracks))
    markup = kb.kb_top_chart(uid, tracks) # Эту функцию нужно вернуть в keyboards.py!
    
    try:
        await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        # Если было фото, а топ чарт без фото -> переотправляем
        await clb.message.delete()
        await clb.message.answer(text, reply_markup=markup, parse_mode="HTML")

# --- HISTORY (Восстановлено) ---
@dp.callback_query(F.data == "my:history")
async def view_history(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    
    # 🔥 Await DB
    history = await Database.get_user_history(uid, limit=10)
    
    if not history:
        await clb.answer(T(uid, 'history_empty', "History is empty"), show_alert=True)
        return
        
    lines = [T(uid, 'history_title', "📜 <b>Search History:</b>")]
    for q in history: 
        lines.append(f"▫️ {q}") # Упростил, если ключа 'history_item' нет
    full_text = "\n".join(lines)
    
    try: 
        await clb.message.edit_text(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")
    except:
        await clb.message.delete()
        await clb.message.answer(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")

@dp.callback_query(F.data == "back:to:main")
async def back_to_main(clb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await open_main_menu(clb.from_user.id, clb.message.chat.id, clb=clb)

@dp.callback_query(F.data == "close_msg")
async def close_msg_handler(clb: types.CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass