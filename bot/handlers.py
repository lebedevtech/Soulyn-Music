import os
import html
import re
import asyncio 
from aiogram import types, F
from aiogram.types import FSInputFile, CallbackQuery, InputMediaPhoto, WebAppInfo, Message
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# Импорт из твоих модулей
from bot.keyboards import app_kb
from bot.loader import dp, bot, logger, user_settings, search_cache, error_cache
from bot.config import ADMIN_ID, LANG_IMG_PATH, SUPPORT_GROUP_ID, GENRES_LIST
from bot.database import Database
from bot.services import search_yt, download_yt, get_lyrics, resolve_meta_to_youtube
from bot.texts import T
import bot.keyboards as kb
from bot.states import Registration, Playlist, Support
from bot.utils import delete_later, format_title, split_playlist_name

BOT_NAME_TEXT = "Soulyn Music"

# Путь к баннеру
BANNER_PATH = os.path.join("bot", "assets", "banner.jpg")
if not os.path.exists(BANNER_PATH):
    BANNER_PATH = os.path.join("assets", "banner.jpg")

# -------------------------------------------------------------------------
# 🔥 НОВЫЙ ХЕНДЛЕР: MINI APP
# Мы ставим его В НАЧАЛО, чтобы поиск музыки не перехватывал команду /app
# -------------------------------------------------------------------------

# Ссылка на твое приложение
WEB_APP_URL = "https://soulyn-music-tma.vercel.app" 

@dp.message(Command("app"))
async def open_app(message: Message):
    await message.answer(
        text=(
            "🚀 <b>Music Genie App</b>\n\n"
            "Нажми кнопку ниже, чтобы открыть плеер будущего! 👇"
        ),
        reply_markup=app_kb(WEB_APP_URL),
        parse_mode="HTML"
    )

# -------------------------------------------------------------------------
# ОСНОВНЫЕ ФУНКЦИИ
# -------------------------------------------------------------------------

async def open_main_menu(uid, chat_id, clb=None, text_key='menu'):
    markup = kb.kb_menu(uid)
    text = T(uid, text_key)
    
    has_banner = os.path.exists(BANNER_PATH)
    photo = FSInputFile(BANNER_PATH) if has_banner else None

    if clb:
        try: await clb.answer()
        except: pass

        try:
            if clb.message.photo and has_banner:
                media = InputMediaPhoto(media=photo, caption=text, parse_mode="HTML")
                await clb.message.edit_media(media, reply_markup=markup)
                Database.set_menu_id(uid, clb.message.message_id)
                return
            
            need_recreate = (has_banner and not clb.message.photo) or (not has_banner and clb.message.photo)
            
            if need_recreate:
                await clb.message.delete()
                if has_banner:
                    msg = await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="HTML")
                else:
                    msg = await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
                Database.set_menu_id(uid, msg.message_id)
                return

            if not has_banner:
                await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
                Database.set_menu_id(uid, clb.message.message_id)
                return
                
        except TelegramBadRequest as e:
            if "message is not modified" in str(e): return 
        except Exception: pass 

    old_menu_id = Database.get_menu_id(uid)
    if old_menu_id:
        try: await bot.delete_message(chat_id, old_menu_id)
        except: pass
    
    if has_banner:
        msg = await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        msg = await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        
    Database.set_menu_id(uid, msg.message_id)

@dp.callback_query(F.data == "close_msg")
async def close_msg_handler(clb: CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass

# --- СТАРТ ---
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    Database.register_user(uid, msg.from_user.username, msg.from_user.first_name)
    user = Database.get_user(uid)
    
    if not user.get("lang"):
        welcome_text = T(uid, 'welcome').format(msg.from_user.first_name)
        if os.path.exists(LANG_IMG_PATH):
            await msg.answer_photo(FSInputFile(LANG_IMG_PATH), caption=welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
        else:
            await msg.answer(welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
    else:
        await open_main_menu(uid, msg.chat.id)

# --- НАВИГАЦИЯ ---
@dp.callback_query(F.data == "back:to:main")
async def back_to_main(clb: CallbackQuery, state: FSMContext):
    await state.clear()
    await open_main_menu(clb.from_user.id, clb.message.chat.id, clb=clb)

@dp.callback_query(F.data == "nav:search")
async def nav_search_handler(clb: CallbackQuery):
    await clb.answer()
    try:
        await clb.message.delete()
        msg = await clb.message.answer(T(clb.from_user.id, 'search_mode_text'), reply_markup=kb.kb_cancel_search(clb.from_user.id), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("set:lang:"))
async def set_lang(clb: CallbackQuery):
    lang = clb.data.split(":")[-1]
    uid = clb.from_user.id
    Database.set_lang(uid, lang)
    await clb.answer(T(uid, 'lang_set'))
    try: await clb.message.delete() 
    except: pass
    await open_main_menu(uid, clb.message.chat.id)

# --- ПЛЕЙЛИСТЫ И УПРАВЛЕНИЕ ---
@dp.callback_query(F.data == "open:playlists")
async def open_playlists(clb: CallbackQuery):
    await clb.answer()
    if clb.message.photo:
        await clb.message.delete()
        await clb.message.answer(T(clb.from_user.id, 'playlists_list'), reply_markup=kb.kb_all_playlists(clb.from_user.id), parse_mode="HTML")
    else:
        try:
            await clb.message.edit_text(T(clb.from_user.id, 'playlists_list'), reply_markup=kb.kb_all_playlists(clb.from_user.id), parse_mode="HTML")
        except TelegramBadRequest: pass

@dp.callback_query(F.data.startswith("viewpl:"))
async def view_playlist(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[1]
    page_num = int(parts[2])
    uid = clb.from_user.id
    user = Database.get_user(uid)
    tracks = user.get("playlists", {}).get(pl_name, [])
    disp_name = T(uid, 'fav_title') if pl_name == "Favorites" else pl_name
    if not tracks: text = T(uid, 'playlist_empty').format(disp_name) 
    else: text = T(uid, 'playlist_view').format(disp_name)
    
    if clb.message.photo:
        await clb.message.delete()
        msg = await clb.message.answer(text, reply_markup=kb.kb_playlist_view(uid, tracks, page_num, pl_name), parse_mode="HTML")
        Database.set_menu_id(uid, msg.message_id)
    else:
        try:
            await clb.message.edit_text(text, reply_markup=kb.kb_playlist_view(uid, tracks, page_num, pl_name), parse_mode="HTML")
            Database.set_menu_id(uid, clb.message.message_id)
        except TelegramBadRequest: pass

@dp.callback_query(F.data.startswith("pl:opts:"))
async def open_playlist_options(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try:
        await clb.message.edit_text(T(uid, 'pl_opts_title').format(pl_name), reply_markup=kb.kb_playlist_options(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("addtr:menu:"))
async def add_track_menu(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    await clb.message.edit_text(T(uid, 'add_track_title').format(pl_name), reply_markup=kb.kb_add_track_choice(uid, pl_name), parse_mode="HTML")

@dp.callback_query(F.data.startswith("addtr:fav:"))
async def add_track_from_fav(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    uid = clb.from_user.id
    markup = kb.kb_select_from_fav(uid, pl_name, page)
    if not markup:
        await clb.answer("Favorites is empty!", show_alert=True)
        return
    await clb.message.edit_text(T(uid, 'select_from_fav'), reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("addtr:save:"))
async def process_add_from_fav(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[2]
    target_pl = parts[3]
    uid = clb.from_user.id
    Database.add_track_to_playlist(uid, target_pl, vid)
    m = await clb.message.answer(T(uid, 'added_to_pl').format(target_pl), parse_mode="HTML")
    asyncio.create_task(delete_later(m))
    clb.data = f"viewpl:{target_pl}:0"
    await view_playlist(clb)

@dp.callback_query(F.data.startswith("addtr:search:"))
async def add_track_search_tip(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    await clb.message.edit_text(T(uid, 'search_tip_pl').format(pl_name), reply_markup=kb.kb_back_to_pl_view(uid, pl_name), parse_mode="HTML")

@dp.callback_query(F.data.startswith("setpl:name:"))
async def rename_playlist_start(clb: CallbackQuery, state: FSMContext):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    await clb.message.delete()
    msg = await clb.message.answer(T(uid, 'pl_enter_new_name'), reply_markup=kb.kb_back_to_pl(uid, pl_name), parse_mode="HTML")
    await state.set_state(Playlist.waiting_for_rename)
    await state.update_data(old_name=pl_name, msg_id=msg.message_id)

@dp.message(Playlist.waiting_for_rename)
async def process_rename(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    new_text = msg.text[:30].strip()
    data = await state.get_data()
    old_name = data['old_name']
    try: await bot.delete_message(msg.chat.id, data['msg_id'])
    except: pass
    try: await msg.delete()
    except: pass
    
    icon, _ = split_playlist_name(old_name)
    if icon: final_name = f"{icon} {new_text}"
    else: final_name = new_text
        
    if Database.rename_playlist(uid, old_name, final_name):
        m = await msg.answer(T(uid, 'pl_renamed').format(final_name), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        await msg.answer(T(uid, 'playlists_list'), reply_markup=kb.kb_all_playlists(uid), parse_mode="HTML")
    else:
        m = await msg.answer(T(uid, 'pl_exists'), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        await msg.answer(T(uid, 'playlists_list'), reply_markup=kb.kb_all_playlists(uid), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("setpl:icon:"))
async def set_icon_start(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try: await clb.message.edit_text(T(uid, 'pl_select_icon'), reply_markup=kb.kb_icon_select(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("doicon:"))
async def set_icon_finish(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    old_pl_name = parts[1]
    new_icon = parts[2]
    uid = clb.from_user.id
    _, base_name = split_playlist_name(old_pl_name)
    new_name = f"{new_icon} {base_name}"
    
    if Database.rename_playlist(uid, old_pl_name, new_name):
        user = Database.get_user(uid)
        tracks = user.get("playlists", {}).get(new_name, [])
        disp_name = T(uid, 'fav_title') if new_name == "Favorites" else new_name
        if not tracks: text = T(uid, 'playlist_empty').format(disp_name) 
        else: text = T(uid, 'playlist_view').format(disp_name)
        await clb.message.edit_text(text, reply_markup=kb.kb_playlist_view(uid, tracks, 0, new_name), parse_mode="HTML")

@dp.callback_query(F.data.startswith("setpl:del:"))
async def delete_playlist_ask(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try: await clb.message.edit_text(T(uid, 'pl_del_confirm').format(pl_name), reply_markup=kb.kb_pl_delete_confirm(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("dodelpl:"))
async def delete_playlist_confirm(clb: CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[1]
    uid = clb.from_user.id
    Database.delete_playlist(uid, pl_name)
    m = await clb.message.answer(T(uid, 'pl_deleted'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))
    await open_playlists(clb)

@dp.callback_query(F.data.startswith("rmtr:"))
async def remove_track(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[1]
    vid = parts[2]
    uid = clb.from_user.id
    try: await clb.message.delete()
    except: pass
    Database.remove_track_from_playlist(uid, pl_name, vid)
    
    menu_id = Database.get_menu_id(uid)
    if menu_id:
        user = Database.get_user(uid)
        tracks = user.get("playlists", {}).get(pl_name, [])
        disp_name = T(uid, 'fav_title') if pl_name == "Favorites" else pl_name
        if not tracks: text = T(uid, 'playlist_empty').format(disp_name)
        else: text = T(uid, 'playlist_view').format(disp_name)
        try: await bot.edit_message_text(chat_id=clb.message.chat.id, message_id=menu_id, text=text, reply_markup=kb.kb_playlist_view(uid, tracks, 0, pl_name), parse_mode="HTML")
        except: pass

    m = await clb.message.answer(T(uid, 'track_removed'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("movetr:ask:"))
async def move_track_ask(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[2]
    from_pl = parts[3]
    uid = clb.from_user.id
    await clb.message.answer(T(uid, 'select_move_target'), reply_markup=kb.kb_move_target(uid, vid, from_pl), parse_mode="HTML")

@dp.callback_query(F.data.startswith("domove:"))
async def move_track_do(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[1]
    from_pl = parts[2]
    to_pl = parts[3]
    uid = clb.from_user.id
    Database.add_track_to_playlist(uid, to_pl, vid)
    Database.remove_track_from_playlist(uid, from_pl, vid)
    await clb.message.delete()
    m = await clb.message.answer(T(uid, 'track_moved'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data == "create:playlist")
async def create_playlist_start(clb: CallbackQuery, state: FSMContext):
    await clb.answer()
    uid = clb.from_user.id
    await clb.message.delete()
    msg = await clb.message.answer(T(uid, 'pl_ask_name'), reply_markup=kb.kb_cancel_create(uid), parse_mode="HTML")
    await state.set_state(Playlist.waiting_for_title)
    await state.update_data(msg_id=msg.message_id)

@dp.message(Playlist.waiting_for_title)
async def process_playlist_title(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    title = msg.text[:30]
    success = Database.create_playlist(uid, title)
    data = await state.get_data()
    try: await bot.delete_message(msg.chat.id, data['msg_id'])
    except: pass
    try: await msg.delete()
    except: pass
    
    if success: 
        m = await msg.answer(T(uid, 'pl_created').format(title), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        user = Database.get_user(uid)
        tracks = [] 
        text = T(uid, 'playlist_empty').format(title)
        menu = await msg.answer(text, reply_markup=kb.kb_playlist_view(uid, tracks, 0, title), parse_mode="HTML")
        Database.set_menu_id(uid, menu.message_id)
    else: 
        m = await msg.answer(T(uid, 'pl_exists'), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        menu = await msg.answer(T(uid, 'menu'), reply_markup=kb.kb_menu(uid), parse_mode="HTML")
        Database.set_menu_id(uid, menu.message_id)
    await state.clear()

@dp.callback_query(F.data.startswith("addpl:"))
async def add_to_playlist_menu(clb: CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    await clb.message.answer(T(uid, 'playlists'), reply_markup=kb.kb_select_playlist(uid, vid), parse_mode="HTML")

@dp.callback_query(F.data.startswith("savepl:"))
async def save_to_playlist(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":", 2)
    vid = parts[1]
    pl_name = parts[2]
    uid = clb.from_user.id
    Database.add_track_to_playlist(uid, pl_name, vid)
    await clb.message.delete()
    m = await clb.message.answer(T(uid, 'added_to_pl').format(pl_name), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("fav:"))
async def add_favorite(clb: CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    Database.add_track_to_playlist(uid, "Favorites", vid)
    new_kb = kb.kb_track(uid, vid, is_liked=True)
    try: await clb.message.edit_reply_markup(reply_markup=new_kb)
    except: pass
    m = await clb.message.answer(T(uid, 'added_to_fav_msg'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("unfav:"))
async def remove_favorite_inline(clb: CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    Database.remove_track_from_playlist(uid, "Favorites", vid)
    new_kb = kb.kb_track(uid, vid, is_liked=False)
    try: await clb.message.edit_reply_markup(reply_markup=new_kb)
    except: pass
    m = await clb.message.answer(T(uid, 'removed_from_fav_msg'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("dl:"))
async def download_handler(clb: CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    raw_vid = ":".join(parts[1:]) 
    uid = clb.from_user.id
    
    if not Database.check_limit(uid):
        await clb.message.answer(T(uid, 'limit_reached'), reply_markup=kb.kb_auth(uid), parse_mode="HTML")
        return
        
    meta_pkg = None
    real_vid = raw_vid
    
    if "spotify:" in raw_vid or "itunes:" in raw_vid:
        if uid in search_cache:
            for item in search_cache[uid]:
                if item['id'] == raw_vid:
                    meta_pkg = item['meta_pkg']
                    resolved_id = await resolve_meta_to_youtube(meta_pkg['artist'], meta_pkg['title'])
                    if resolved_id:
                        real_vid = resolved_id
                    break
    
    cached = Database.get_track(real_vid)
    
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}"
    caption = f"<a href='{bot_link}'>🎧 via {BOT_NAME_TEXT}</a>"

    if cached:
        Database.update_stats(uid, genre=cached.get('genre'))
        user = Database.get_user(uid)
        is_liked = real_vid in user.get("playlists", {}).get("Favorites", [])
        
        await clb.message.answer_audio(
            cached['file_id'], 
            caption=caption,
            reply_markup=kb.kb_track(uid, real_vid, None, is_liked=is_liked),
            parse_mode="HTML"
        )
        await open_main_menu(uid, clb.message.chat.id)
        return

    loading_msg = await clb.message.edit_text(T(uid, 'dl'), parse_mode="HTML")
    
    track_path = None
    thumb_path = None
    
    try:
        track = await download_yt(real_vid, meta_pkg=meta_pkg)
        
        if track and os.path.exists(track['path']):
            track_path = track['path']
            thumb_path = track.get('thumb_path')
            
            file_size_mb = os.path.getsize(track_path) / (1024 * 1024)
            if file_size_mb > 49:
                raise Exception("File too large (>50MB)")

            thumb = FSInputFile(thumb_path) if thumb_path and os.path.exists(thumb_path) else None
            audio = FSInputFile(track_path)
            
            final_vid = os.path.basename(track_path).replace(".mp3", "")
            
            user = Database.get_user(uid)
            favs = user.get("playlists", {}).get("Favorites", [])
            is_liked = final_vid in favs

            sent = await clb.message.answer_audio(
                audio,
                title=track['title'], performer=track['artist'], thumbnail=thumb,
                caption=caption,
                reply_markup=kb.kb_track(uid, final_vid, None, is_liked=is_liked),
                parse_mode="HTML"
            )
            
            Database.cache_track(final_vid, sent.audio.file_id, track['title'], track['artist'], meta=track.get('meta'))
            Database.update_stats(uid, genre=track.get('meta', {}).get('genre'))
            
            try: await loading_msg.delete()
            except: pass
            
            await open_main_menu(uid, clb.message.chat.id)
        else:
            raise Exception("Download failed (File not found)")
            
    except Exception as e:
        logger.error(f"DL Error: {e}")
        error_cache[uid] = str(e)
        
        err_msg = "❌ <b>Не удалось скачать трек.</b>"
        if "too large" in str(e).lower():
            err_msg = "❌ <b>Файл слишком большой (>50MB).</b>"
        elif "duration" in str(e).lower():
            err_msg = "❌ <b>Трек слишком длинный (>20 мин).</b>"

        try:
            await loading_msg.edit_text(
                err_msg, 
                reply_markup=kb.kb_error_report(uid),
                parse_mode="HTML"
            )
        except: 
            await clb.message.answer(err_msg, reply_markup=kb.kb_error_report(uid), parse_mode="HTML")
            
    finally:
        if track_path and os.path.exists(track_path):
            try: os.remove(track_path)
            except: pass
        if thumb_path and os.path.exists(thumb_path):
            try: os.remove(thumb_path)
            except: pass

@dp.callback_query(F.data == "report:error")
async def report_error_handler(clb: CallbackQuery):
    uid = clb.from_user.id
    err_text = error_cache.get(uid, "Unknown error")
    user = Database.get_user(uid)
    username = f"@{user.get('username')}" if user else "Unknown"
    
    report_text = (
        f"🐞 <b>BUG REPORT</b>\n\n"
        f"👤 <b>User:</b> {username} (ID: {uid})\n"
        f"🚨 <b>Error:</b>\n<code>{err_text}</code>"
    )
    
    try:
        await bot.send_message(SUPPORT_GROUP_ID, report_text, parse_mode="HTML")
        await clb.answer("✅ Отчет отправлен разработчикам!", show_alert=True)
        await clb.message.delete()
        await open_main_menu(uid, clb.message.chat.id)
    except Exception as e:
        await clb.answer(f"❌ Failed to send report: {e}", show_alert=True)

@dp.callback_query(F.data == "my:profile")
async def my_profile(clb: CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    user = Database.get_user(uid)
    if clb.message.photo:
        await clb.message.delete()
        await clb.message.answer(T(uid, 'profile').format(user.get('nickname', 'User'), user.get('downloads_total', 0), "...", 0), reply_markup=kb.kb_profile(uid), parse_mode="HTML")
    else:
        try:
            await clb.message.edit_text(T(uid, 'profile').format(user.get('nickname', 'User'), user.get('downloads_total', 0), "...", 0), reply_markup=kb.kb_profile(uid), parse_mode="HTML")
        except TelegramBadRequest: pass

@dp.callback_query(F.data == "settings")
async def settings(clb: CallbackQuery):
    await clb.answer()
    if clb.message.photo:
        await clb.message.delete()
        await clb.message.answer(T(clb.from_user.id, 'settings'), reply_markup=kb.kb_settings(clb.from_user.id), parse_mode="HTML")
    else:
        try: await clb.message.edit_text(T(clb.from_user.id, 'settings'), reply_markup=kb.kb_settings(clb.from_user.id), parse_mode="HTML")
        except: pass

@dp.callback_query(F.data == "change:lang:menu") 
async def change_lang_menu(clb: CallbackQuery):
    await clb.answer()
    user = Database.get_user(clb.from_user.id)
    name = user.get("nickname") if user and user.get("nickname") else clb.from_user.first_name
    try: await clb.message.edit_text(T(clb.from_user.id, 'welcome').format(name), reply_markup=kb.kb_lang(), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data == "auth:guest")
async def auth_guest(clb: CallbackQuery):
    await clb.answer()
    await clb.message.edit_text(T(clb.from_user.id, 'guest_warning'), reply_markup=kb.kb_guest_confirm(clb.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "confirm:guest")
async def confirm_guest(clb: CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    await clb.message.delete()
    await clb.message.answer(T(uid, 'guest_mode'), parse_mode="HTML")
    await open_main_menu(uid, clb.message.chat.id)

@dp.callback_query(F.data == "auth:reg")
async def auth_reg(clb: CallbackQuery, state: FSMContext):
    await clb.answer()
    uid = clb.from_user.id
    await clb.message.delete()
    msg = await clb.message.answer(T(uid, 'ask_nick'), parse_mode="HTML")
    await state.set_state(Registration.waiting_for_nickname)
    await state.update_data(msg_id=msg.message_id)

@dp.message(Registration.waiting_for_nickname)
async def process_nickname(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    nickname = msg.text[:20]
    await state.update_data(nickname=nickname)
    data = await state.get_data()
    try: await bot.delete_message(msg.chat.id, data['msg_id'])
    except: pass
    try: await msg.delete()
    except: pass
    user = Database.get_user(uid)
    pre_selected = []
    if user and "fav_genres" in user:
        sorted_fav = sorted(user["fav_genres"], key=user["fav_genres"].get, reverse=True)
        valid_fav = [g for g in sorted_fav if g in GENRES_LIST]
        pre_selected = valid_fav[:3]
    await state.update_data(selected_genres=pre_selected)
    await msg.answer(T(uid, 'ask_genres'), reply_markup=kb.kb_genres(uid, pre_selected), parse_mode="HTML")

@dp.callback_query(F.data.startswith("genre:"))
async def process_genre(clb: CallbackQuery, state: FSMContext):
    action = clb.data.split(":")[1]
    uid = clb.from_user.id
    data = await state.get_data()
    selected = data.get("selected_genres", [])
    if action == "done":
        await clb.answer()
        nickname = data.get("nickname", "User")
        Database.set_profile(uid, nickname, genres=selected)
        await clb.message.delete()
        await clb.message.answer(T(uid, 'reg_success').format(nickname), parse_mode="HTML")
        await state.clear()
        await open_main_menu(uid, clb.message.chat.id)
        return
    if action in selected: selected.remove(action)
    else: selected.append(action)
    await state.update_data(selected_genres=selected)
    try: await clb.message.edit_reply_markup(reply_markup=kb.kb_genres(uid, selected))
    except: pass 
    await clb.answer()

@dp.callback_query(F.data.startswith("lyrics:"))
async def lyrics(clb: CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    info = Database.get_track(vid)
    uid = clb.from_user.id
    
    if not info: 
        await clb.message.answer("⚠️ Информация о треке не найдена.")
        return

    status_msg = await clb.message.answer(T(uid, 'searching_lyrics'), parse_mode="HTML")
    text = await get_lyrics(info['artist'], info['title'])
    
    if text:
        try: await status_msg.delete()
        except: pass

        text = text.replace("Embed", "")
        text = re.sub(r'\d+$', '', text).strip()
        safe_text = html.escape(text)
        safe_artist = html.escape(info['artist'])
        safe_title = html.escape(info['title'])
        header = f"🎤 <b>{safe_artist} - {safe_title}</b>\n\n"
        full_message = header + safe_text
        if len(full_message) > 4096: full_message = full_message[:4090] + "..."
        await clb.message.answer(full_message, parse_mode="HTML", reply_markup=kb.kb_close(uid))
    else:
        try: await status_msg.edit_text("😔 <b>Текст этой песни не найден.</b>", parse_mode="HTML")
        except: pass

@dp.callback_query(F.data == "delete:message")
async def delete_message(clb: CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass

@dp.callback_query(F.data == "del:acc:ask")
async def delete_account_ask(clb: CallbackQuery):
    await clb.answer()
    await clb.message.edit_text(T(clb.from_user.id, 'del_confirm'), reply_markup=kb.kb_del_confirm(clb.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "del:acc:confirm")
async def delete_account_confirm(clb: CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    Database.soft_delete_user(uid)
    await clb.message.delete()
    await clb.message.answer(T(uid, 'del_success'), parse_mode="HTML")
    await open_main_menu(uid, clb.message.chat.id)

@dp.callback_query(F.data == "restore:acc")
async def restore_account(clb: CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    if Database.restore_user(uid):
        await clb.message.delete()
        m = await clb.message.answer(T(uid, 'restored'), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        await open_main_menu(uid, clb.message.chat.id)

@dp.message(Command("ticket"))
@dp.callback_query(F.data == "open:ticket")
async def open_ticket_start(event: types.Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        msg = event.message
        uid = event.from_user.id
        await event.answer()
    else:
        msg = event
        uid = event.from_user.id

    old_menu_id = Database.get_menu_id(uid)
    if old_menu_id:
        try: await bot.delete_message(msg.chat.id, old_menu_id)
        except: pass

    try: await msg.delete()
    except: pass
    
    sent_msg = await bot.send_message(
        msg.chat.id, 
        T(uid, 'ticket_ask'), 
        reply_markup=kb.kb_cancel_ticket(uid), 
        parse_mode="HTML"
    )
    await state.update_data(ticket_msg_id=sent_msg.message_id)
    await state.set_state(Support.waiting_for_message)

@dp.callback_query(F.data == "ticket:cancel")
async def cancel_ticket(clb: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await clb.message.delete()
    except: pass
    await open_main_menu(clb.from_user.id, clb.message.chat.id)

@dp.message(Support.waiting_for_message, F.chat.type == "private")
async def process_ticket_sent(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    user = Database.get_user(uid)
    username = f"@{msg.from_user.username}" if msg.from_user.username else "No Username"
    
    data = await state.get_data()
    if 'ticket_msg_id' in data:
        try: await bot.delete_message(msg.chat.id, data['ticket_msg_id'])
        except: pass

    header = f"📩 <b>Тикет</b> #id{uid}\n👤 <b>{msg.from_user.full_name}</b> ({username})"
    
    try:
        if msg.text:
            final_text = f"{header}\n\n{msg.html_text}"
            await bot.send_message(SUPPORT_GROUP_ID, final_text, parse_mode="HTML")
        else:
            user_caption = msg.html_text if msg.caption else ""
            final_caption = f"{header}\n\n{user_caption}"
            if len(final_caption) > 1000: final_caption = final_caption[:950] + "..."
            await msg.copy_to(SUPPORT_GROUP_ID, caption=final_caption, parse_mode="HTML")

        confirm_msg = await msg.answer(T(uid, 'ticket_sent'), parse_mode="HTML")
        asyncio.create_task(delete_later(confirm_msg, 5))
        await open_main_menu(uid, msg.chat.id)
        
    except Exception as e:
        logger.error(f"Ticket Error: {e}")
        await msg.answer("❌ Ошибка отправки. Попробуйте только текст.", parse_mode="HTML")
    
    await state.clear()

@dp.message(F.chat.id == SUPPORT_GROUP_ID, F.reply_to_message)
async def admin_reply_handler(msg: types.Message):
    topic_msg = msg.reply_to_message
    user_id = None
    content_to_check = topic_msg.text or topic_msg.caption or ""
    match = re.search(r"#id\s*(\d+)", content_to_check)
    
    if match:
        user_id = int(match.group(1))
        try:
            if msg.text:
                formatted_text = T(user_id, 'ticket_reply').format(msg.html_text)
                await bot.send_message(user_id, formatted_text, parse_mode="HTML")
            elif msg.photo or msg.video or msg.document or msg.audio:
                header = "👨‍💻 <b>Ответ от поддержки:</b>"
                user_caption = msg.html_text if msg.caption else ""
                final_caption = f"{header}\n\n{user_caption}"
                if len(final_caption) > 1000: final_caption = final_caption[:950] + "..."
                await msg.copy_to(user_id, caption=final_caption, parse_mode="HTML")
            else:
                await bot.send_message(user_id, "👨‍💻 <b>Ответ от поддержки:</b> 👇", parse_mode="HTML")
                await msg.copy_to(user_id)

            await msg.react([types.ReactionTypeEmoji(emoji="👍")])
            
        except Exception as e:
            await msg.reply(f"❌ Не доставлено! Ошибка: {e}")
    else:
        await msg.reply("⚠️ <b>ID не найден!</b>")

@dp.message(Command("admin"))
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    users, tracks = Database.get_stats()
    total_dl = sum(u.get("downloads_total", 0) for u in users.values())
    await msg.answer(f"📊 <b>Stats:</b>\n👥 Total: {len(users)}\n💾 DLs: {total_dl}", parse_mode="HTML")

@dp.message(Command("maintenance_alert"))
async def send_maintenance_alert(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    
    MAINTENANCE_IMG_PATH = "maintenance.jpg"
    if not os.path.exists(MAINTENANCE_IMG_PATH):
        await msg.answer(f"❌ Файл {MAINTENANCE_IMG_PATH} не найден!")
        return

    users = Database.get_all_user_ids() if hasattr(Database, 'get_all_user_ids') else []
    if not users:
        users_dict, _ = Database.get_stats()
        users = [int(u) for u in users_dict.keys()]

    await msg.answer(f"📢 Рассылка для {len(users)} чел...")
    photo = FSInputFile(MAINTENANCE_IMG_PATH)
    
    caption = (
        "🇷🇺 <b>Важное объявление</b>\n"
        "Технические работы до субботы. Скоро будет новая версия!\n\n"
        "🇺🇸 <b>Important Announcement</b>\n"
        "Technical maintenance until Saturday. New version coming soon!"
    )
    
    cnt = 0
    for uid in users:
        try:
            await bot.send_photo(uid, photo, caption=caption, parse_mode="HTML")
            cnt += 1
            await asyncio.sleep(0.05)
        except: pass
        
    await msg.answer(f"✅ Готово: {cnt}")

@dp.message(Command("announce_fix"))
async def announce_fix_handler(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    users_dict, _ = Database.get_stats()
    
    cnt = 0
    for uid in users_dict:
        try:
            text = "👋 <b>Мы вернулись!</b>\nПоиск снова работает."
            await bot.send_message(uid, text, parse_mode="HTML")
            cnt += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.answer(f"✅ Готово: {cnt}")

# --- ПОИСК (ВАЖНО: ДОЛЖЕН БЫТЬ В САМОМ КОНЦЕ) ---
@dp.message(F.text, StateFilter(None), F.chat.type == "private")
async def text_search(msg: types.Message):
    uid = msg.from_user.id
    Database.register_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    old_id = Database.get_menu_id(uid)
    if old_id:
        try: await bot.delete_message(msg.chat.id, old_id)
        except: pass

    status_msg = await msg.answer(T(uid, 'search').format(msg.text), parse_mode="HTML")
    res = await search_yt(msg.text)
    
    if res:
        search_cache[uid] = res
        await status_msg.edit_text(T(uid, 'select'), reply_markup=kb.kb_search(uid, res, 0), parse_mode="HTML")
    else:
        await status_msg.edit_text(T(uid, '404'), parse_mode="HTML")
        await asyncio.sleep(5)
        try: await status_msg.delete()
        except: pass
        await open_main_menu(uid, msg.chat.id)

@dp.callback_query(F.data == "delete:search")
async def delete_search_btn(clb: CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass
    await open_main_menu(clb.from_user.id, clb.message.chat.id)

@dp.callback_query(F.data.startswith("page:"))
async def search_pagination(clb: CallbackQuery):
    await clb.answer()
    try:
        page = int(clb.data.split(":")[1])
        uid = clb.from_user.id
        if uid in search_cache:
            res = search_cache[uid]
            await clb.message.edit_text(T(uid, 'select'), reply_markup=kb.kb_search(uid, res, page), parse_mode="HTML")
        else:
            await clb.answer("⚠️ Результаты устарели.", show_alert=True)
    except: pass