import os
import hashlib
import re
import asyncio
from aiogram import types, F
from aiogram.types import FSInputFile, InlineQueryResultArticle, InputTextMessageContent, LinkPreviewOptions
from aiogram.filters import CommandStart, CommandObject, StateFilter, Command
from aiogram.fsm.context import FSMContext

from bot.loader import dp, bot, logger, search_cache
from bot.database import Database
from bot.services import search_yt, download_yt, recognize_media, resolve_meta_to_youtube, get_lyrics
from bot.texts import T
import bot.keyboards as kb
from bot.handlers.common import open_main_menu, start_normal, BANNER_PATH, BOT_NAME_TEXT

LISTEN_DICT = {
    'ru': "🎧 Слушать", 'uk': "🎧 Слухати", 'be': "🎧 Слухаць",
    'en': "🎧 Listen", 'de': "🎧 Anhören", 'es': "🎧 Escuchar",
    'fr': "🎧 Écouter", 'it': "🎧 Ascoltare", 'pl': "🎧 Słuchać",
    'pt': "🎧 Ouvir", 'tr': "🎧 Dinle", 'id': "🎧 Dengarkan",
    'ar': "🎧 استمع", 'fa': "🎧 گوش دادن", 'uz': "🎧 Tinglash",
    'kz': "🎧 Тыңдау"
}

@dp.message(CommandStart(deep_link=True))
async def start_deep_link(msg: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    await Database.register_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    args = command.args
    if args and args.startswith("dl_"):
        raw_vid = args[3:]
        real_vid = raw_vid.replace("__", ":")
        status_msg = await msg.answer(T(uid, 'dl'), parse_mode="HTML")
        await _process_download(uid, msg.chat.id, real_vid, status_msg)
        return

    # Если deep link не dl_, обычный старт
    await start_normal(msg, state)

@dp.message(F.text.startswith("🆔"), F.chat.type == "private")
async def auto_download_trigger(msg: types.Message):
    uid = msg.from_user.id
    try:
        parts = msg.text.split()
        safe_id = parts[1]
        real_vid = safe_id.replace("__", ":")
    except: return

    try: await msg.delete()
    except: pass

    status_msg = await msg.answer(T(uid, 'dl'), parse_mode="HTML")
    await _process_download(uid, msg.chat.id, real_vid, status_msg)

@dp.message(F.text, StateFilter(None), F.chat.type == "private")
async def text_search(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    if msg.text.startswith("⎯") or msg.text.startswith("🎵"): return

    if "http" in msg.text:
        status_msg = await msg.answer(T(uid, 'dl'), parse_mode="HTML")
        res = await search_yt(msg.text)
        if res and len(res) > 0:
            await _process_download(uid, msg.chat.id, res[0]['id'], status_msg)
        else:
            await status_msg.edit_text(T(uid, '404'), parse_mode="HTML")
        return
    # Если не ссылка — ничего не делаем (поиск через inline)
    return

@dp.inline_query()
async def inline_search_handler(query: types.InlineQuery):
    text = query.query.strip()
    uid = query.from_user.id
    is_private_chat = query.chat_type == 'sender'
    
    user_lang_code = query.from_user.language_code
    if user_lang_code: user_lang_code = user_lang_code[:2]
    btn_text = LISTEN_DICT.get(user_lang_code, LISTEN_DICT['en'])
    
    if len(text) < 2: return 

    await Database.add_search_history(uid, text)

    results = await search_yt(text)
    if not results: return

    search_cache[uid] = results 

    articles = []
    bot_username = (await bot.get_me()).username

    for track in results[:20]:
        result_id = hashlib.md5(track['id'].encode()).hexdigest()
        safe_id = track['id'].replace(":", "__")
        
        if track.get('meta_pkg'):
            display_title = track['meta_pkg']['title']
            display_artist = track['meta_pkg']['artist']
            cover_url = track['meta_pkg']['meta'].get('cover')
        else:
            raw_title = track['title']
            if " - " in raw_title:
                parts = raw_title.split(" - ", 1)
                display_artist = parts[0].strip()
                display_title = parts[1].strip()
            else:
                display_artist = track['uploader']
                display_title = raw_title
            cover_url = f"https://i.ytimg.com/vi/{track['id']}/hqdefault.jpg"

        junk_words = ["iTunes", "Topic", "VEVO", "Official", "Audio", "Video", "Source", "Auto-generated"]
        for junk in junk_words: display_artist = display_artist.replace(junk, "").strip()
        display_artist = display_artist.strip(" -|,.")
        if len(display_artist) < 2: display_artist = "Unknown Artist"

        if is_private_chat:
            trigger_text = f"🆔 {safe_id} ⏳ {display_title}"
            article = InlineQueryResultArticle(
                id=result_id,
                title=display_title,
                description=display_artist,
                thumbnail_url=cover_url,
                input_message_content=InputTextMessageContent(
                    message_text=trigger_text, 
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            )
        else:
            card_caption = f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n<b>{display_title}</b>\n{display_artist}"
            dl_link = f"https://t.me/{bot_username}?start=dl_{safe_id}"
            article = InlineQueryResultArticle(
                id=result_id,
                title=display_title,
                description=display_artist,
                thumbnail_url=cover_url,
                input_message_content=InputTextMessageContent(
                    message_text=card_caption, 
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                ),
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text=btn_text, url=dl_link)]
                ])
            )
        articles.append(article)

    await query.answer(articles, cache_time=1, is_personal=True)

@dp.message(F.voice | F.audio | F.video | F.video_note)
async def shazam_handler(msg: types.Message):
    uid = msg.from_user.id
    status_msg = await msg.answer("🎧 <b>Слушаю...</b>", parse_mode="HTML")
    
    file_path = None
    try:
        if msg.voice: file_id = msg.voice.file_id
        elif msg.video: file_id = msg.video.file_id
        elif msg.video_note: file_id = msg.video_note.file_id
        elif msg.audio: file_id = msg.audio.file_id
        else: return

        file = await bot.get_file(file_id)
        file_path = f"downloads/temp_{uid}_{file.file_unique_id}"
        await bot.download_file(file.file_path, file_path)
        
        track_name = await recognize_media(file_path)
        
        if track_name:
            await status_msg.edit_text(f"🎉 <b>Нашел:</b> {track_name}\n🔍 <i>Ищу лучшее качество...</i>", parse_mode="HTML")
            await Database.add_search_history(uid, track_name)
            res = await search_yt(track_name)
            
            if res:
                search_cache[uid] = res
                best_match = res[0]
                await _process_download(uid, msg.chat.id, best_match['id'], status_msg)
            else:
                await status_msg.edit_text(f"🤔 Shazam нашел <b>{track_name}</b>, но скачать не вышло.", parse_mode="HTML")
        else:
            await status_msg.edit_text("😔 <b>Не удалось распознать.</b>", parse_mode="HTML")
            await asyncio.sleep(5)
            try: await status_msg.delete()
            except: pass
            
    except Exception as e:
        logger.error(f"SHAZAM ERROR: {e}")
        try: await status_msg.edit_text("❌ Ошибка при распознавании.", parse_mode="HTML")
        except: pass
    finally:
        if file_path and os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

async def _process_download(uid, chat_id, raw_vid, message_to_edit=None):
    if not await Database.check_limit(uid):
        limit_text = T(uid, 'limit_reached')
        if message_to_edit: await message_to_edit.edit_text(limit_text, reply_markup=kb.kb_auth(uid), parse_mode="HTML")
        else: await bot.send_message(chat_id, limit_text, reply_markup=kb.kb_auth(uid), parse_mode="HTML")
        return

    meta_pkg = None
    real_vid = raw_vid
    
    if uid in search_cache:
        for item in search_cache[uid]:
            if item['id'] == raw_vid:
                meta_pkg = item.get('meta_pkg')
                break
    
    if ":" in str(raw_vid) and not meta_pkg:
        try:
            restore_res = await search_yt(raw_vid)
            if restore_res: meta_pkg = restore_res[0].get('meta_pkg')
        except: pass

    db_lookup_id = real_vid
    if meta_pkg:
        resolved = await resolve_meta_to_youtube(meta_pkg['artist'], meta_pkg['title'])
        if resolved: db_lookup_id = resolved

    cached = await Database.get_track(db_lookup_id)
    bot_info = await bot.get_me()
    caption = f"<a href='https://t.me/{bot_info.username}'>🎧 via {BOT_NAME_TEXT}</a>"

    if cached and cached.get('file_id') and cached['file_id'] != 'FILE_ID_UNKNOWN':
        await Database.update_stats(uid, genre=cached.get('genre'))
        await Database.increment_track_popularity(db_lookup_id)
        if cached.get('title') and cached.get('artist'):
            await Database.add_search_history(uid, f"{cached['artist']} - {cached['title']}")

        user = await Database.get_user(uid)
        is_liked = db_lookup_id in user.get("playlists", {}).get("Favorites", [])
        if message_to_edit: 
            try: await message_to_edit.delete() 
            except: pass
        
        markup = await kb.kb_track(uid, db_lookup_id, None, is_liked=is_liked)
        await bot.send_audio(chat_id, cached['file_id'], caption=caption, reply_markup=markup, parse_mode="HTML")
        return

    if message_to_edit: 
        try: await message_to_edit.edit_text(T(uid, 'dl'), parse_mode="HTML")
        except: pass
    else: message_to_edit = await bot.send_message(chat_id, T(uid, 'dl'), parse_mode="HTML")
    
    track_path = None
    thumb_path = None
    try:
        track = await download_yt(real_vid, meta_pkg=meta_pkg)
        if track and os.path.exists(track['path']):
            track_path = track['path']
            thumb_path = track.get('thumb_path')
            thumb = FSInputFile(thumb_path) if thumb_path and os.path.exists(thumb_path) else None
            audio = FSInputFile(track_path)
            final_vid = os.path.basename(track_path).replace(".mp3", "")
            
            user = await Database.get_user(uid)
            favs = user.get("playlists", {}).get("Favorites", [])
            is_liked = final_vid in favs

            markup = await kb.kb_track(uid, final_vid, None, is_liked=is_liked)
            sent = await bot.send_audio(chat_id, audio, title=track['title'], performer=track['artist'], thumbnail=thumb, caption=caption, reply_markup=markup, parse_mode="HTML")
            
            await Database.cache_track(final_vid, sent.audio.file_id, track['title'], track['artist'], meta=track.get('meta'))
            await Database.update_stats(uid, genre=track.get('meta', {}).get('genre'))
            await Database.add_search_history(uid, f"{track['artist']} - {track['title']}")
            try: await message_to_edit.delete()
            except: pass
        else: raise Exception("Download failed")
    except Exception as e:
        logger.error(f"DL Error: {e}")
        try: await message_to_edit.edit_text(T(uid, 'err'), reply_markup=kb.kb_error_report(uid), parse_mode="HTML")
        except: await bot.send_message(chat_id, T(uid, 'err'), reply_markup=kb.kb_error_report(uid), parse_mode="HTML")
    finally:
        if track_path and os.path.exists(track_path):
            try: os.remove(track_path)
            except: pass
        if thumb_path and os.path.exists(thumb_path):
            try: os.remove(thumb_path)
            except: pass

@dp.callback_query(F.data.startswith("dl:"))
async def download_handler_btn(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    raw_vid = ":".join(parts[1:]) 
    uid = clb.from_user.id
    await _process_download(uid, clb.message.chat.id, raw_vid, clb.message)

@dp.callback_query(F.data == "delete:search")
async def delete_search_btn(clb: types.CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass
    await open_main_menu(clb.from_user.id, clb.message.chat.id)

@dp.callback_query(F.data.startswith("page:"))
async def search_pagination(clb: types.CallbackQuery):
    await clb.answer()

@dp.callback_query(F.data.startswith("lyrics:"))
async def lyrics(clb: types.CallbackQuery):
    await clb.answer()
    try:
        vid = clb.data.split(":", 1)[1] 
        uid = clb.from_user.id
        
        info = await Database.get_track(vid)
        
        if not info:
            try:
                res = await search_yt(vid)
                if res and res[0]['id'] == vid:
                    await Database.cache_track(vid, "FILE_ID_UNKNOWN", res[0]['title'], res[0].get('uploader', 'Artist'))
                    info = await Database.get_track(vid)
            except: pass

        if not info: 
            await clb.message.answer("⚠️ Информация о треке не найдена в базе.")
            return

        status_msg = await clb.message.answer(T(uid, 'searching_lyrics'), parse_mode="HTML")
        
        text = info.get('lyrics')
        if not text:
            text = await get_lyrics(info['artist'], info['title'])
            if text: await Database.save_lyrics(vid, text)
        
        if text:
            try: await status_msg.delete()
            except: pass
            
            text = text.replace("Embed", "")
            text = re.sub(r'\d*Embed$', '', text)
            text = re.sub(r'\d+$', '', text).strip()
            
            import html
            safe_text = html.escape(text)
            safe_artist = html.escape(info['artist'] or 'Unknown')
            safe_title = html.escape(info['title'] or 'Unknown')
            
            header = f"🎤 <b>{safe_artist} - {safe_title}</b>\n\n"
            full_message = header + safe_text
            if len(full_message) > 4096: full_message = full_message[:4090] + "..."
            
            await clb.message.answer(full_message, parse_mode="HTML", reply_markup=kb.kb_close(uid))
        else:
            try: await status_msg.edit_text("😔 <b>Текст этой песни не найден.</b>", parse_mode="HTML")
            except: pass
            
    except Exception as e:
        logger.error(f"Lyrics error: {e}")
        try: await clb.message.answer("❌ Ошибка при поиске текста.")
        except: pass