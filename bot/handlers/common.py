import os
import asyncio
from aiogram import types, F
from aiogram.types import FSInputFile, InputMediaPhoto
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from bot.loader import dp, bot, user_settings
from bot.database import Database
from bot.config import ADMIN_ID, GENRES_LIST
from bot.texts import T
import bot.keyboards as kb
from bot.states import Registration
from bot.utils import delete_later

# --- Константа имени бота (используется в user_search.py) ---
BOT_NAME_TEXT = "Soulyn Music"

# Пути к картинкам
BANNER_PATH = os.path.join("assets", "banner.jpg")
if not os.path.exists(BANNER_PATH):
    BANNER_PATH = os.path.join("bot", "assets", "banner.jpg")
    if not os.path.exists(BANNER_PATH):
        BANNER_PATH = None

LANG_IMG_PATH = os.path.join("assets", "lang.png")
if not os.path.exists(LANG_IMG_PATH):
    LANG_IMG_PATH = os.path.join("bot", "assets", "lang.png")
    if not os.path.exists(LANG_IMG_PATH):
        LANG_IMG_PATH = None


# --- START (без deep link) ---
async def start_normal(msg: types.Message, state: FSMContext):
    """Общая логика /start без deep link. Вызывается из user_search.py тоже."""
    await state.clear()
    uid = msg.from_user.id
    
    args = msg.text.split()[1:] if len(msg.text.split()) > 1 else []
    referrer = int(args[0]) if args and args[0].isdigit() and int(args[0]) != uid else None
    
    await Database.register_user(uid, msg.from_user.username, msg.from_user.full_name, referrer_id=referrer)
    
    user = await Database.get_user(uid)
    
    if not user or not user.get('lang'):
        welcome_text = T(uid, 'welcome', 'Welcome! Choose language:').format(msg.from_user.first_name)
        if LANG_IMG_PATH and os.path.exists(LANG_IMG_PATH):
            await msg.answer_photo(FSInputFile(LANG_IMG_PATH), caption=welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
        else:
            await msg.answer(welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
    else:
        await open_main_menu(uid, msg.chat.id)


@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    # Проверяем deep link аргументы — если есть dl_, обработка в user_search.py
    if len(msg.text.split()) > 1 and msg.text.split()[1].startswith("dl_"):
        return  # Обрабатывается в user_search.py через CommandStart(deep_link=True)
    await start_normal(msg, state)


# --- ВЫБОР ЯЗЫКА ---
# 🔥 FIX: keyboards.py отправляет "set:lang:ru", а не "lang:ru"
@dp.callback_query(F.data.startswith("set:lang:"))
async def set_language(clb: types.CallbackQuery):
    lang_code = clb.data.split(":")[2]
    uid = clb.from_user.id
    await Database.set_lang(uid, lang_code)
    await clb.answer(f"Language: {lang_code.upper()}")
    try: await clb.message.delete()
    except: pass
    await open_main_menu(uid, clb.message.chat.id)


# --- MENU HELPER ---
async def open_main_menu(uid, chat_id, clb=None, text_key='menu'):
    # 🔥 FIX: kb_menu is async, needs await
    markup = await kb.kb_menu(uid)
    text = T(uid, text_key)
    
    has_banner = BANNER_PATH and os.path.exists(BANNER_PATH)
    photo = FSInputFile(BANNER_PATH) if has_banner else None

    if clb:
        try: await clb.answer()
        except: pass
        
        is_media_message = clb.message.audio or clb.message.voice or clb.message.video
        if not is_media_message:
            try:
                if clb.message.photo and has_banner:
                    media = InputMediaPhoto(media=photo, caption=text, parse_mode="HTML")
                    await clb.message.edit_media(media, reply_markup=markup)
                    await Database.set_menu_id(uid, clb.message.message_id)
                    return
                elif not clb.message.photo and not has_banner:
                    await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
                    await Database.set_menu_id(uid, clb.message.message_id)
                    return
            except Exception: 
                pass 
        
        try: await clb.message.delete()
        except: pass

    old_menu_id = await Database.get_menu_id(uid)
    if old_menu_id:
        try: await bot.delete_message(chat_id, old_menu_id)
        except: pass
    
    if has_banner:
        msg = await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        msg = await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
    
    await Database.set_menu_id(uid, msg.message_id)


# --- TOP CHART ---
@dp.callback_query(F.data == "view:top")
async def view_top_chart(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    
    tracks = await Database.get_top_tracks(limit=10)
    
    if not tracks:
        await clb.answer(T(uid, 'top_chart_empty', "Top chart is empty!"), show_alert=True)
        return

    text = T(uid, 'top_chart_title', "🔥 <b>Top {count} Popular Tracks:</b>").format(count=len(tracks))
    markup = kb.kb_top_chart(uid, tracks)
    
    try:
        await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        try: await clb.message.delete()
        except: pass
        await clb.message.answer(text, reply_markup=markup, parse_mode="HTML")


# --- HISTORY ---
@dp.callback_query(F.data == "my:history")
async def view_history(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    
    history = await Database.get_user_history(uid, limit=10)
    
    if not history:
        await clb.answer(T(uid, 'history_empty', "History is empty"), show_alert=True)
        return
        
    lines = [T(uid, 'history_title', "📜 <b>Search History:</b>")]
    for q in history: 
        lines.append(f"▫️ {q}")
    full_text = "\n".join(lines)
    
    try: 
        await clb.message.edit_text(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")
    except:
        try: await clb.message.delete()
        except: pass
        await clb.message.answer(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")


# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "my:profile")
async def view_profile(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    user = await Database.get_user(uid)
    
    name = user.get('nickname') or user.get('full_name') or "User"
    total = user.get('downloads_total', 0)
    text = T(uid, 'profile').format(name, total)
    
    try:
        await clb.message.edit_text(text, reply_markup=kb.kb_profile(uid), parse_mode="HTML")
    except:
        try: await clb.message.delete()
        except: pass
        await clb.message.answer(text, reply_markup=kb.kb_profile(uid), parse_mode="HTML")


# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "settings")
@dp.message(Command("settings"))
async def settings_handler(event: types.Message | types.CallbackQuery):
    uid = event.from_user.id
    text = T(uid, 'settings')
    markup = kb.kb_settings(uid)
    
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        try:
            await event.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except:
            try: await event.message.delete()
            except: pass
            await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=markup, parse_mode="HTML")


# --- СМЕНА ЯЗЫКА (из настроек) ---
@dp.callback_query(F.data == "change:lang:menu")
async def change_lang_menu(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    try:
        await clb.message.edit_text("🌍 Choose language:", reply_markup=kb.kb_lang(uid), parse_mode="HTML")
    except:
        await clb.message.answer("🌍 Choose language:", reply_markup=kb.kb_lang(uid), parse_mode="HTML")


# --- HELP: MEDIA ---
@dp.callback_query(F.data == "help:media")
async def help_media(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    text = T(uid, 'help_media')
    try:
        await clb.message.edit_text(text, reply_markup=kb.kb_back_to_main(uid), parse_mode="HTML")
    except:
        try: await clb.message.delete()
        except: pass
        await clb.message.answer(text, reply_markup=kb.kb_back_to_main(uid), parse_mode="HTML")


# --- РЕГИСТРАЦИЯ ---
@dp.callback_query(F.data == "auth:reg")
async def auth_reg_start(clb: types.CallbackQuery, state: FSMContext):
    await clb.answer()
    uid = clb.from_user.id
    try: await clb.message.delete()
    except: pass
    msg = await clb.message.answer(T(uid, 'ask_nick'), parse_mode="HTML")
    await state.set_state(Registration.waiting_for_nickname)
    await state.update_data(msg_id=msg.message_id)

@dp.message(Registration.waiting_for_nickname)
async def process_nickname(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    nickname = msg.text[:30].strip()
    data = await state.get_data()
    try: await bot.delete_message(msg.chat.id, data.get('msg_id'))
    except: pass
    try: await msg.delete()
    except: pass
    
    await state.update_data(nickname=nickname, selected_genres=[])
    sent = await msg.answer(T(uid, 'ask_genres'), reply_markup=kb.kb_genres(uid, []), parse_mode="HTML")
    await state.update_data(msg_id=sent.message_id)
    await state.set_state(Registration.waiting_for_genres)

@dp.callback_query(Registration.waiting_for_genres, F.data.startswith("genre:"))
async def process_genre_select(clb: types.CallbackQuery, state: FSMContext):
    genre = clb.data.split(":")[1]
    uid = clb.from_user.id
    data = await state.get_data()
    selected = data.get('selected_genres', [])
    
    if genre == "done":
        await clb.answer()
        nickname = data.get('nickname', clb.from_user.first_name)
        await Database.set_profile(uid, nickname, selected)
        # Обновляем RAM кэш
        if uid in user_settings:
            user_settings[uid]['status'] = 'user'
        try: await clb.message.delete()
        except: pass
        m = await clb.message.answer(T(uid, 'reg_success'), parse_mode="HTML")
        asyncio.create_task(delete_later(m, 3))
        await state.clear()
        await open_main_menu(uid, clb.message.chat.id)
        return
    
    if genre in selected:
        selected.remove(genre)
    else:
        selected.append(genre)
    
    await state.update_data(selected_genres=selected)
    await clb.answer(f"{'✅' if genre in selected else '❌'} {genre}")
    
    try:
        await clb.message.edit_reply_markup(reply_markup=kb.kb_genres(uid, selected))
    except: pass


# --- ГОСТЬ ---
@dp.callback_query(F.data == "confirm:guest")
async def confirm_guest(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    try: await clb.message.delete()
    except: pass
    await open_main_menu(uid, clb.message.chat.id)


# --- УДАЛЕНИЕ АККАУНТА ---
@dp.callback_query(F.data == "del:acc:ask")
async def del_acc_ask(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    try:
        await clb.message.edit_text(T(uid, 'del_confirm'), reply_markup=kb.kb_del_confirm(uid), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data == "del:acc:confirm")
async def del_acc_confirm(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    await Database.soft_delete_user(uid)
    try: await clb.message.delete()
    except: pass
    m = await clb.message.answer(T(uid, 'del_success'), reply_markup=kb.kb_restore(uid), parse_mode="HTML")


# --- ВОССТАНОВЛЕНИЕ ---
@dp.callback_query(F.data == "restore:acc")
async def restore_acc(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    # Восстанавливаем статус
    await Database.set_profile(uid, clb.from_user.first_name, [])
    try: await clb.message.delete()
    except: pass
    m = await clb.message.answer(T(uid, 'restored'), parse_mode="HTML")
    asyncio.create_task(delete_later(m, 3))
    await open_main_menu(uid, clb.message.chat.id)


# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back:to:main")
async def back_to_main(clb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await open_main_menu(clb.from_user.id, clb.message.chat.id, clb=clb)

@dp.callback_query(F.data == "close_msg")
async def close_msg_handler(clb: types.CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass

@dp.callback_query(F.data == "ignore")
async def ignore_handler(clb: types.CallbackQuery):
    await clb.answer()

@dp.callback_query(F.data == "delete:message")
async def delete_message_handler(clb: types.CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass