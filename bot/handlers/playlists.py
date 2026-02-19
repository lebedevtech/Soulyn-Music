import asyncio
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.loader import dp, bot
from bot.database import Database
from bot.texts import T
import bot.keyboards as kb
from bot.states import Playlist
from bot.utils import delete_later, split_playlist_name
from bot.handlers.common import open_main_menu

@dp.callback_query(F.data == "open:playlists")
async def open_playlists(clb: types.CallbackQuery):
    await clb.answer()
    markup = await kb.kb_all_playlists(clb.from_user.id)
    if clb.message.photo:
        await clb.message.delete()
        await clb.message.answer(T(clb.from_user.id, 'playlists_list'), reply_markup=markup, parse_mode="HTML")
    else:
        try: await clb.message.edit_text(T(clb.from_user.id, 'playlists_list'), reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest: pass

@dp.callback_query(F.data.startswith("viewpl:"))
async def view_playlist(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[1]
    page_num = int(parts[2])
    uid = clb.from_user.id
    user = await Database.get_user(uid)
    tracks = user.get("playlists", {}).get(pl_name, [])
    disp_name = T(uid, 'fav_title') if pl_name == "Favorites" else pl_name
    text = T(uid, 'playlist_empty').format(disp_name) if not tracks else T(uid, 'playlist_view').format(disp_name)
    
    markup = await kb.kb_playlist_view(uid, tracks, page_num, pl_name)
    
    if clb.message.photo:
        await clb.message.delete()
        msg = await clb.message.answer(text, reply_markup=markup, parse_mode="HTML")
        await Database.set_menu_id(uid, msg.message_id)
    else:
        try:
            await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
            await Database.set_menu_id(uid, clb.message.message_id)
        except TelegramBadRequest: pass

@dp.callback_query(F.data.startswith("pl:opts:"))
async def open_playlist_options(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try: await clb.message.edit_text(T(uid, 'pl_opts_title').format(pl_name), reply_markup=kb.kb_playlist_options(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("addtr:menu:"))
async def add_track_menu(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    await clb.message.edit_text(T(uid, 'add_track_title').format(pl_name), reply_markup=kb.kb_add_track_choice(uid, pl_name), parse_mode="HTML")

@dp.callback_query(F.data.startswith("addtr:fav:"))
async def add_track_from_fav(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    uid = clb.from_user.id
    markup = await kb.kb_select_from_fav(uid, pl_name, page)
    if not markup:
        await clb.answer("Favorites is empty!", show_alert=True)
        return
    await clb.message.edit_text(T(uid, 'select_from_fav'), reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("addtr:save:"))
async def process_add_from_fav(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[2]
    target_pl = parts[3]
    uid = clb.from_user.id
    await Database.add_track_to_playlist(uid, target_pl, vid)
    m = await clb.message.answer(T(uid, 'added_to_pl').format(target_pl), parse_mode="HTML")
    asyncio.create_task(delete_later(m))
    clb.data = f"viewpl:{target_pl}:0"
    await view_playlist(clb)

@dp.callback_query(F.data.startswith("addtr:search:"))
async def add_track_search_tip(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    await clb.message.edit_text(T(uid, 'search_tip_pl').format(pl_name), reply_markup=kb.kb_back_to_pl_view(uid, pl_name), parse_mode="HTML")

@dp.callback_query(F.data.startswith("setpl:name:"))
async def rename_playlist_start(clb: types.CallbackQuery, state: FSMContext):
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
        
    if await Database.rename_playlist(uid, old_name, final_name):
        m = await msg.answer(T(uid, 'pl_renamed').format(final_name), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        markup = await kb.kb_all_playlists(uid)
        await msg.answer(T(uid, 'playlists_list'), reply_markup=markup, parse_mode="HTML")
    else:
        m = await msg.answer(T(uid, 'pl_exists'), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        markup = await kb.kb_all_playlists(uid)
        await msg.answer(T(uid, 'playlists_list'), reply_markup=markup, parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("setpl:icon:"))
async def set_icon_start(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try: await clb.message.edit_text(T(uid, 'pl_select_icon'), reply_markup=kb.kb_icon_select(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("doicon:"))
async def set_icon_finish(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    old_pl_name = parts[1]
    new_icon = parts[2]
    uid = clb.from_user.id
    _, base_name = split_playlist_name(old_pl_name)
    new_name = f"{new_icon} {base_name}"
    
    if await Database.rename_playlist(uid, old_pl_name, new_name):
        user = await Database.get_user(uid)
        tracks = user.get("playlists", {}).get(new_name, [])
        disp_name = T(uid, 'fav_title') if new_name == "Favorites" else new_name
        text = T(uid, 'playlist_empty').format(disp_name) if not tracks else T(uid, 'playlist_view').format(disp_name)
        markup = await kb.kb_playlist_view(uid, tracks, 0, new_name)
        await clb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("setpl:del:"))
async def delete_playlist_ask(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[2]
    uid = clb.from_user.id
    try: await clb.message.edit_text(T(uid, 'pl_del_confirm').format(pl_name), reply_markup=kb.kb_pl_delete_confirm(uid, pl_name), parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("dodelpl:"))
async def delete_playlist_confirm(clb: types.CallbackQuery):
    await clb.answer()
    pl_name = clb.data.split(":")[1]
    uid = clb.from_user.id
    await Database.delete_playlist(uid, pl_name)
    m = await clb.message.answer(T(uid, 'pl_deleted'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))
    await open_playlists(clb)

@dp.callback_query(F.data.startswith("rmtr:"))
async def remove_track(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    pl_name = parts[1]
    vid = parts[2]
    uid = clb.from_user.id
    try: await clb.message.delete()
    except: pass
    await Database.remove_track_from_playlist(uid, pl_name, vid)
    
    menu_id = await Database.get_menu_id(uid)
    if menu_id:
        user = await Database.get_user(uid)
        tracks = user.get("playlists", {}).get(pl_name, [])
        disp_name = T(uid, 'fav_title') if pl_name == "Favorites" else pl_name
        text = T(uid, 'playlist_empty').format(disp_name) if not tracks else T(uid, 'playlist_view').format(disp_name)
        markup = await kb.kb_playlist_view(uid, tracks, 0, pl_name)
        try: await bot.edit_message_text(chat_id=clb.message.chat.id, message_id=menu_id, text=text, reply_markup=markup, parse_mode="HTML")
        except: pass

    m = await clb.message.answer(T(uid, 'track_removed'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("movetr:ask:"))
async def move_track_ask(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[2]
    from_pl = parts[3]
    uid = clb.from_user.id
    markup = await kb.kb_move_target(uid, vid, from_pl)
    await clb.message.answer(T(uid, 'select_move_target'), reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("domove:"))
async def move_track_do(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":")
    vid = parts[1]
    from_pl = parts[2]
    to_pl = parts[3]
    uid = clb.from_user.id
    await Database.add_track_to_playlist(uid, to_pl, vid)
    await Database.remove_track_from_playlist(uid, from_pl, vid)
    await clb.message.delete()
    m = await clb.message.answer(T(uid, 'track_moved'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data == "create:playlist")
async def create_playlist_start(clb: types.CallbackQuery, state: FSMContext):
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
    success = await Database.create_playlist(uid, title)
    data = await state.get_data()
    try: await bot.delete_message(msg.chat.id, data['msg_id'])
    except: pass
    try: await msg.delete()
    except: pass
    
    if success: 
        m = await msg.answer(T(uid, 'pl_created').format(title), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        text = T(uid, 'playlist_empty').format(title)
        markup = await kb.kb_playlist_view(uid, [], 0, title)
        menu = await msg.answer(text, reply_markup=markup, parse_mode="HTML")
        await Database.set_menu_id(uid, menu.message_id)
    else: 
        m = await msg.answer(T(uid, 'pl_exists'), parse_mode="HTML")
        asyncio.create_task(delete_later(m))
        # 🔥 FIX: kb_menu is async
        markup = await kb.kb_menu(uid)
        menu = await msg.answer(T(uid, 'menu'), reply_markup=markup, parse_mode="HTML")
        await Database.set_menu_id(uid, menu.message_id)
    await state.clear()

@dp.callback_query(F.data.startswith("addpl:"))
async def add_to_playlist_menu(clb: types.CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    # 🔥 FIX: kb_select_playlist is now async
    markup = await kb.kb_select_playlist(uid, vid)
    await clb.message.answer(T(uid, 'playlists'), reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("savepl:"))
async def save_to_playlist(clb: types.CallbackQuery):
    await clb.answer()
    parts = clb.data.split(":", 2)
    vid = parts[1]
    pl_name = parts[2]
    uid = clb.from_user.id
    await Database.add_track_to_playlist(uid, pl_name, vid)
    await clb.message.delete()
    m = await clb.message.answer(T(uid, 'added_to_pl').format(pl_name), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("fav:"))
async def add_favorite(clb: types.CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    await Database.add_track_to_playlist(uid, "Favorites", vid)
    new_kb = await kb.kb_track(uid, vid, is_liked=True)
    try: await clb.message.edit_reply_markup(reply_markup=new_kb)
    except: pass
    m = await clb.message.answer(T(uid, 'added_to_fav_msg'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))

@dp.callback_query(F.data.startswith("unfav:"))
async def remove_favorite_inline(clb: types.CallbackQuery):
    await clb.answer()
    vid = clb.data.split(":")[1]
    uid = clb.from_user.id
    await Database.remove_track_from_playlist(uid, "Favorites", vid)
    new_kb = await kb.kb_track(uid, vid, is_liked=False)
    try: await clb.message.edit_reply_markup(reply_markup=new_kb)
    except: pass
    m = await clb.message.answer(T(uid, 'removed_from_fav_msg'), parse_mode="HTML")
    asyncio.create_task(delete_later(m))