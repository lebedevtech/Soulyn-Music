import asyncio
import re
import os
import matplotlib
# 🔥 Исправление для серверов и Windows (без GUI)
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

from bot.loader import dp, bot, logger, error_cache
from bot.database import Database
from bot.config import ADMIN_ID, SUPPORT_GROUP_ID, GENRES_LIST
from bot.texts import T
import bot.keyboards as kb
from bot.states import Registration, Support, Broadcast, AdminActions
from bot.utils import delete_later
from bot.handlers.common import open_main_menu

# --- ГЛАВНОЕ МЕНЮ АДМИНА ---
@dp.message(Command("admin"))
@dp.callback_query(F.data == "admin:main")
async def admin_panel(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if user_id != ADMIN_ID: return
    
    # Асинхронный вызов статистики
    users, tracks = await Database.get_stats()
    total_dl = sum(u.get("downloads_total", 0) for u in users.values())
    
    text = (
        f"👨‍💻 <b>ADMIN PANEL v2.0</b>\n\n"
        f"👥 <b>Users:</b> {len(users)}\n"
        f"🎵 <b>Tracks:</b> {len(tracks)}\n"
        f"💾 <b>Downloads:</b> {total_dl}\n"
    )
    
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=kb.kb_admin_panel(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=kb.kb_admin_panel(), parse_mode="HTML")

# --- СТАТИСТИКА (ГРАФИКИ) ---
@dp.callback_query(F.data == "admin:stats")
async def admin_stats(clb: types.CallbackQuery):
    await clb.answer("Генерирую график...")
    data = await Database.get_daily_registrations()
    
    if not data:
        await clb.message.answer("📉 Нет данных для графика.")
        return

    # Рисуем график
    dates = list(data.keys())
    counts = list(data.values())
    
    plt.figure(figsize=(10, 5))
    plt.plot(dates, counts, marker='o', linestyle='-', color='#1DB954')
    plt.title('Новые пользователи за 7 дней')
    plt.grid(True, linestyle='--', alpha=0.6)
    
    if not os.path.exists("downloads"): os.makedirs("downloads")
    chart_path = "downloads/stats_chart.png"
    plt.savefig(chart_path)
    plt.close()
    
    await clb.message.answer_photo(
        FSInputFile(chart_path),
        caption="📊 <b>Статистика регистраций</b>",
        reply_markup=kb.kb_admin_back(),
        parse_mode="HTML"
    )
    try: os.remove(chart_path)
    except: pass

@dp.callback_query(F.data == "admin:top_queries")
async def admin_top_queries(clb: types.CallbackQuery):
    top = await Database.get_popular_searches(limit=15)
    text = "🔥 <b>Что ищут люди (но не находят):</b>\n\n"
    if not top:
        text += "Пока пусто."
    for q, cnt in top:
        text += f"▫️ {q} — <b>{cnt}</b>\n"
    
    await clb.message.edit_text(text, reply_markup=kb.kb_admin_back(), parse_mode="HTML")

# --- УПРАВЛЕНИЕ ЮЗЕРАМИ ---
@dp.callback_query(F.data == "admin:users")
async def admin_users_start(clb: types.CallbackQuery, state: FSMContext):
    await clb.message.edit_text(
        "👤 <b>Управление пользователями</b>\n\nВведите Telegram ID пользователя или перешлите сообщение от него.",
        reply_markup=kb.kb_admin_back(),
        parse_mode="HTML"
    )
    await state.set_state(AdminActions.waiting_for_user_id)

@dp.message(AdminActions.waiting_for_user_id)
async def admin_find_user(msg: types.Message, state: FSMContext):
    try:
        if msg.forward_from: target_id = msg.forward_from.id
        else: target_id = int(msg.text.strip())
    except:
        await msg.answer("❌ Некорректный ID.")
        return

    user = await Database.get_user(target_id)
    if not user:
        await msg.answer("❌ Пользователь не найден в базе.")
        return

    text = (
        f"👤 <b>User Info:</b>\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Name: {user['full_name']}\n"
        f"Nick: {user['nickname']}\n"
        f"Status: <b>{user['status']}</b>\n"
        f"Banned: {'YES 🔴' if user.get('is_banned') else 'NO 🟢'}\n"
        f"Joined: {user['join_date']}\n"
        f"Downloads: {user['downloads_total']}"
    )
    
    is_banned = user.get('is_banned', 0)
    is_premium = user['status'] == 'premium'
    
    await msg.answer(
        text, 
        reply_markup=kb.kb_admin_user_manage(target_id, is_banned, is_premium),
        parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data.startswith("adm:"))
async def admin_user_action(clb: types.CallbackQuery):
    action, target_id = clb.data.split(":")[1], int(clb.data.split(":")[2])
    
    if action == "ban":
        await Database.set_user_ban_status(target_id, True)
        await clb.answer("🔴 Пользователь забанен!")
    elif action == "unban":
        await Database.set_user_ban_status(target_id, False)
        await clb.answer("🟢 Пользователь разбанен!")
    elif action == "prem":
        await Database.set_user_premium(target_id, True)
        await clb.answer("⭐️ Премиум выдан!")
    elif action == "unprem":
        await Database.set_user_premium(target_id, False)
        await clb.answer("⬇️ Премиум снят!")
        
    user = await Database.get_user(target_id)
    text = (
        f"👤 <b>User Info:</b>\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Name: {user['full_name']}\n"
        f"Nick: {user['nickname']}\n"
        f"Status: <b>{user['status']}</b>\n"
        f"Banned: {'YES 🔴' if user.get('is_banned') else 'NO 🟢'}\n"
        f"Joined: {user['join_date']}\n"
        f"Downloads: {user['downloads_total']}"
    )
    is_banned = user.get('is_banned', 0)
    is_premium = user['status'] == 'premium'
    
    await clb.message.edit_text(text, reply_markup=kb.kb_admin_user_manage(target_id, is_banned, is_premium), parse_mode="HTML")

# --- РАССЫЛКА ---
@dp.callback_query(F.data == "admin:broadcast")
async def start_broadcast(clb: types.CallbackQuery, state: FSMContext):
    await clb.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправьте пост (текст, фото или пересланное сообщение).",
        reply_markup=kb.kb_admin_back(),
        parse_mode="HTML"
    )
    await state.set_state(Broadcast.waiting_for_content)

@dp.message(Broadcast.waiting_for_content)
async def process_broadcast_content(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    
    await state.update_data(msg_id=msg.message_id, chat_id=msg.chat.id)
    
    await msg.answer("👀 <b>Предпросмотр:</b>", parse_mode="HTML")
    try: await msg.copy_to(chat_id=msg.chat.id)
    except: pass
    
    await msg.answer("Добавить кнопку-ссылку?", reply_markup=kb.kb_broadcast_actions())
    await state.set_state(Broadcast.waiting_for_confirm)

@dp.callback_query(Broadcast.waiting_for_confirm, F.data == "broadcast:add_btn")
async def broadcast_add_btn(clb: types.CallbackQuery, state: FSMContext):
    await clb.message.edit_text("Отправьте текст кнопки и ссылку через пробел.\nПример: `Канал https://t.me/channel`", parse_mode="Markdown")
    await state.set_state(Broadcast.waiting_for_button)

@dp.message(Broadcast.waiting_for_button)
async def process_broadcast_btn(msg: types.Message, state: FSMContext):
    try:
        text, url = msg.text.split(" ", 1)
        markup = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text=text, url=url.strip())]])
        await state.update_data(reply_markup=markup)
        
        data = await state.get_data()
        await msg.answer("👀 <b>С кнопкой:</b>", parse_mode="HTML")
        await bot.copy_message(msg.chat.id, msg.chat.id, data['msg_id'], reply_markup=markup)
        
        await msg.answer("Отправляем?", reply_markup=kb.kb_broadcast_confirm())
        await state.set_state(Broadcast.waiting_for_confirm)
    except:
        await msg.answer("❌ Ошибка формата. Попробуй еще раз: `Текст Ссылка`")

@dp.callback_query(Broadcast.waiting_for_confirm, F.data == "broadcast:send")
async def broadcast_send(clb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get('msg_id')
    chat_id = data.get('chat_id')
    markup = data.get('reply_markup')
    
    await clb.message.edit_text("⏳ <b>Рассылка...</b>", parse_mode="HTML")
    users_dict, _ = await Database.get_stats()
    
    success = 0
    blocked = 0
    for uid in users_dict.keys():
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=msg_id, reply_markup=markup)
            success += 1
            await asyncio.sleep(0.05) # Анти-флуд
        except: blocked += 1
            
    await clb.message.answer(f"✅ <b>Готово!</b>\n📬: {success}\n🚫: {blocked}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(Broadcast.waiting_for_confirm, F.data == "broadcast:cancel")
async def broadcast_cancel(clb: types.CallbackQuery, state: FSMContext):
    await clb.message.edit_text("❌ Отменено.")
    await state.clear()

# --- ТИКЕТЫ ---
@dp.callback_query(F.data == "report:error")
async def report_error_handler(clb: types.CallbackQuery):
    uid = clb.from_user.id
    err_text = error_cache.get(uid, "Unknown error")
    report_text = f"🐞 <b>BUG</b> ID:{uid}\n<code>{err_text}</code>"
    try:
        await bot.send_message(SUPPORT_GROUP_ID, report_text, parse_mode="HTML")
        await clb.answer("✅ Отправлено!", show_alert=True)
        await clb.message.delete()
    except: pass

@dp.message(Command("ticket"))
@dp.callback_query(F.data == "open:ticket")
async def open_ticket_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    uid = event.from_user.id
    if isinstance(event, types.CallbackQuery): await event.answer(); msg = event.message
    else: msg = event
    
    sent_msg = await bot.send_message(msg.chat.id, T(uid, 'ticket_ask'), reply_markup=kb.kb_cancel_ticket(uid), parse_mode="HTML")
    await state.update_data(ticket_msg_id=sent_msg.message_id)
    await state.set_state(Support.waiting_for_message)

@dp.callback_query(F.data == "ticket:cancel")
async def cancel_ticket(clb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try: await clb.message.delete()
    except: pass
    await open_main_menu(clb.from_user.id, clb.message.chat.id)

@dp.message(Support.waiting_for_message, F.chat.type == "private")
async def process_ticket_sent(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    data = await state.get_data()
    try: await bot.delete_message(msg.chat.id, data['ticket_msg_id'])
    except: pass
    
    header = f"📩 <b>Ticket</b> #id{uid}\n👤 {msg.from_user.full_name}"
    try:
        if msg.text: await bot.send_message(SUPPORT_GROUP_ID, f"{header}\n\n{msg.html_text}", parse_mode="HTML")
        else: await msg.copy_to(SUPPORT_GROUP_ID, caption=f"{header}\n\n{msg.caption or ''}", parse_mode="HTML")
        confirm = await msg.answer(T(uid, 'ticket_sent'), parse_mode="HTML")
        asyncio.create_task(delete_later(confirm, 5))
        await open_main_menu(uid, msg.chat.id)
    except: await msg.answer("❌ Error sending ticket.")
    await state.clear()

@dp.message(F.chat.id == SUPPORT_GROUP_ID, F.reply_to_message)
async def admin_reply_handler(msg: types.Message):
    match = re.search(r"#id\s*(\d+)", msg.reply_to_message.text or msg.reply_to_message.caption or "")
    if match:
        user_id = int(match.group(1))
        try:
            if msg.text: await bot.send_message(user_id, T(user_id, 'ticket_reply').format(msg.html_text), parse_mode="HTML")
            else: await msg.copy_to(user_id, caption="👨‍💻 <b>Support Reply:</b>\n" + (msg.caption or ""), parse_mode="HTML")
            await msg.react([types.ReactionTypeEmoji(emoji="👍")])
        except: await msg.reply("❌ User blocked bot.")