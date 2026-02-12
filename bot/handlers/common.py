import os
from aiogram import types, F
from aiogram.types import FSInputFile, InputMediaPhoto
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from bot.loader import dp, bot
from bot.database import Database
from bot.config import LANG_IMG_PATH
from bot.texts import T
import bot.keyboards as kb

BOT_NAME_TEXT = "Soulyn Music"
BANNER_PATH = os.path.join("bot", "assets", "banner.jpg")
if not os.path.exists(BANNER_PATH): BANNER_PATH = os.path.join("assets", "banner.jpg")

@dp.callback_query(F.data == "view:top")
async def view_top_chart(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    
    # AWAIT Database
    tracks = await Database.get_top_tracks(limit=10)
    
    if not tracks:
        await clb.answer(T(uid, 'top_chart_empty'), show_alert=True)
        return

    text = T(uid, 'top_chart_title').format(count=len(tracks))
    try:
        await clb.message.edit_text(text, reply_markup=kb.kb_top_chart(uid, tracks), parse_mode="HTML")
    except:
        await clb.message.delete()
        await clb.message.answer(text, reply_markup=kb.kb_top_chart(uid, tracks), parse_mode="HTML")

@dp.callback_query(F.data == "my:history")
async def view_history(clb: types.CallbackQuery):
    await clb.answer()
    uid = clb.from_user.id
    history = await Database.get_user_history(uid, limit=10)
    
    if not history:
        await clb.answer(T(uid, 'history_empty'), show_alert=True)
        return
        
    lines = [T(uid, 'history_title')]
    for q in history: lines.append(T(uid, 'history_item').format(q))
    full_text = "\n".join(lines)
    
    try: await clb.message.edit_text(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")
    except:
        await clb.message.delete()
        await clb.message.answer(full_text, reply_markup=kb.kb_history_back(uid), parse_mode="HTML")

async def open_main_menu(uid, chat_id, clb=None, text_key='menu'):
    # AWAIT kb_menu
    markup = await kb.kb_menu(uid)
    text = T(uid, text_key)
    has_banner = os.path.exists(BANNER_PATH)
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
                await clb.message.delete()
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

@dp.callback_query(F.data == "help:media")
async def help_media_handler(clb: types.CallbackQuery):
    await open_main_menu(clb.from_user.id, clb.message.chat.id, clb=None, text_key='help_media')
    last_msg_id = await Database.get_menu_id(clb.from_user.id)
    if last_msg_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=clb.message.chat.id,
                message_id=last_msg_id,
                reply_markup=kb.kb_back_to_main(clb.from_user.id)
            )
        except: pass

async def start_normal(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    user = await Database.get_user(uid)
    if not user or not user.get("lang"):
        welcome_text = T(uid, 'welcome').format(msg.from_user.first_name)
        if os.path.exists(LANG_IMG_PATH):
            await msg.answer_photo(FSInputFile(LANG_IMG_PATH), caption=welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
        else:
            await msg.answer(welcome_text, reply_markup=kb.kb_lang(), parse_mode="HTML")
    else:
        await open_main_menu(uid, msg.chat.id)

@dp.callback_query(F.data == "back:to:main")
async def back_to_main(clb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await open_main_menu(clb.from_user.id, clb.message.chat.id, clb=clb)

@dp.callback_query(F.data == "close_msg")
async def close_msg_handler(clb: types.CallbackQuery):
    await clb.answer()
    try: await clb.message.delete()
    except: pass