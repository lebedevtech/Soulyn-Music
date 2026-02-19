import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.texts import T
from bot.config import CHANNEL_LINK, GENRES_LIST
from bot.utils import format_title, split_playlist_name
from bot.database import Database

# --- ГЛАВНОЕ МЕНЮ (ASYNC) ---
async def kb_menu(uid):
    kb = InlineKeyboardBuilder()
    user = await Database.get_user(uid)
    
    kb.button(text=T(uid, 'btn_search_live'), switch_inline_query_current_chat="")
    kb.button(text=T(uid, 'btn_links_media'), callback_data="help:media")
    kb.button(text=T(uid, 'btn_top_chart'), callback_data="view:top")
    
    kb.button(text=T(uid, 'btn_playlists'), callback_data="open:playlists")
    
    status = user.get("status") if user else "guest"
    if status in ["user", "premium", "admin"]:
        kb.button(text=T(uid, 'btn_profile'), callback_data="my:profile")
    else:
        kb.button(text=T(uid, 'btn_reg'), callback_data="auth:reg")
    
    kb.button(text=T(uid, 'btn_settings'), callback_data="settings")
    kb.button(text=T(uid, 'btn_support'), callback_data="open:ticket")
    
    kb.adjust(1, 2, 2, 2) 
    return kb.as_markup()

# --- ТРЕК (ASYNC) ---
async def kb_track(uid, vid, from_playlist=None, is_liked=False):
    kb = InlineKeyboardBuilder()
    
    if from_playlist != "Favorites":
        kb.button(text="💔" if is_liked else "❤️", callback_data=f"{'unfav' if is_liked else 'fav'}:{vid}")
    
    kb.button(text=T(uid, 'add_to_pl'), callback_data=f"addpl:{vid}")
    kb.button(text=T(uid, 'btn_lyrics_short'), callback_data=f"lyrics:{vid}")
    
    user = await Database.get_user(uid)
    status = user.get("status") if user else "guest"
    
    if status in ["user", "premium", "admin"]:
        if from_playlist:
            kb.button(text=T(uid, 'btn_remove_track'), callback_data=f"rmtr:{from_playlist}:{vid}")
            kb.button(text=T(uid, 'btn_move_track'), callback_data=f"movetr:ask:{vid}:{from_playlist}")
            if from_playlist == "Favorites":
                kb.adjust(1, 2)
            else:
                kb.adjust(2, 2)
        else:
            kb.adjust(2, 1)
    else:
        kb.adjust(2, 1)
        
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_search_more'), switch_inline_query_current_chat=""),
           InlineKeyboardButton(text=T(uid, 'btn_to_menu'), callback_data="back:to:main"))
    return kb.as_markup()

# --- ПЛЕЙЛИСТЫ (ASYNC) ---
async def kb_all_playlists(uid):
    user = await Database.get_user(uid)
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'pl_create'), callback_data="create:playlist")
    
    if user and user.get("playlists"):
        for pl_name in user["playlists"]:
            if pl_name == "Favorites":
                label = T(uid, 'btn_fav_icon')
            else:
                icon, clean_name = split_playlist_name(pl_name)
                label = f"{icon} {clean_name}" if icon else f"📂 {clean_name}"
            kb.button(text=label, callback_data=f"viewpl:{pl_name}:0")
    
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="back:to:main"))
    return kb.as_markup()

async def kb_playlist_view(uid, tracks, page=0, pl_name="Favorites"):
    kb = InlineKeyboardBuilder()
    if tracks:
        total = math.ceil(len(tracks) / 5)
        start, end = page * 5, (page + 1) * 5
        
        for vid in tracks[start:end]:
            info = await Database.get_track(vid)
            if info:
                title = format_title(info.get('title'), info.get('artist'))
                if len(title) > 35: title = title[:32] + "..."
                kb.button(text=f"🎵 {title}", callback_data=f"dl:{vid}")
        
        kb.adjust(1)
        row = []
        if page > 0: row.append(InlineKeyboardButton(text="⬅️", callback_data=f"viewpl:{pl_name}:{page-1}"))
        row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total}", callback_data="ignore"))
        if page < total - 1: row.append(InlineKeyboardButton(text="➡️", callback_data=f"viewpl:{pl_name}:{page+1}"))
        kb.row(*row)

    if pl_name != "Favorites":
        kb.row(
            InlineKeyboardButton(text=T(uid, 'btn_pl_add_track'), callback_data=f"addtr:menu:{pl_name}"),
            InlineKeyboardButton(text=T(uid, 'btn_pl_opts'), callback_data=f"pl:opts:{pl_name}")
        )
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_playlists'), callback_data="open:playlists"))
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="back:to:main"))
    return kb.as_markup()

async def kb_select_from_fav(uid, target_pl, page=0):
    user = await Database.get_user(uid)
    tracks = user.get("playlists", {}).get("Favorites", [])
    if not tracks: return None
    
    total = math.ceil(len(tracks) / 5)
    start, end = page * 5, (page + 1) * 5
    kb = InlineKeyboardBuilder()
    
    for vid in tracks[start:end]:
        info = await Database.get_track(vid)
        if info:
            title = format_title(info.get('title'), info.get('artist'))
            if len(title) > 35: title = title[:32] + "..."
            kb.button(text=f"➕ {title}", callback_data=f"addtr:save:{vid}:{target_pl}")
            
    kb.adjust(1)
    row = []
    if page > 0: row.append(InlineKeyboardButton(text="⬅️", callback_data=f"addtr:fav:{target_pl}:{page-1}"))
    row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total}", callback_data="ignore"))
    if page < total - 1: row.append(InlineKeyboardButton(text="➡️", callback_data=f"addtr:fav:{target_pl}:{page+1}"))
    kb.row(*row)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data=f"addtr:menu:{target_pl}"))
    return kb.as_markup()

async def kb_move_target(uid, vid, from_pl):
    user = await Database.get_user(uid)
    kb = InlineKeyboardBuilder()
    if user and user.get("playlists"):
        for pl_name in user["playlists"]:
            if pl_name == from_pl: continue 
            if pl_name == "Favorites":
                label = T(uid, 'btn_fav_icon')
            else:
                icon, clean_name = split_playlist_name(pl_name)
                label = f"{icon} {clean_name}" if icon else f"📂 {clean_name}"
            kb.button(text=label, callback_data=f"domove:{vid}:{from_pl}:{pl_name}")
    kb.button(text=T(uid, 'btn_close'), callback_data="delete:message")
    kb.adjust(1)
    return kb.as_markup()

# --- ВЫБОР ПЛЕЙЛИСТА (для кнопки "Добавить в плейлист") ---
# 🔥 FIX: Сделано async, чтобы подгружать плейлисты из БД
async def kb_select_playlist(uid, vid):
    user = await Database.get_user(uid)
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_fav_icon'), callback_data=f"savepl:{vid}:Favorites")
    
    # Показываем все плейлисты пользователя
    if user and user.get("playlists"):
        for pl_name in user["playlists"]:
            if pl_name == "Favorites": continue
            icon, clean_name = split_playlist_name(pl_name)
            label = f"{icon} {clean_name}" if icon else f"📂 {clean_name}"
            kb.button(text=label, callback_data=f"savepl:{vid}:{pl_name}")
    
    kb.button(text=T(uid, 'pl_create'), callback_data="create:playlist")
    kb.button(text=T(uid, 'btn_close'), callback_data="close_msg")
    kb.adjust(1)
    return kb.as_markup()

# --- ЛЕГКИЕ КЛАВИАТУРЫ (SYNC) ---

def kb_top_chart(uid, tracks):
    kb = InlineKeyboardBuilder()
    for track in tracks:
        title = format_title(track.get('title'), track.get('artist'))
        if len(title) > 30: title = title[:27] + "..."
        kb.button(text=f"🔥 {title}", callback_data=f"dl:{track['id']}")
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="back:to:main"))
    return kb.as_markup()

def kb_admin_panel():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin:stats")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="👤 Управление юзерами", callback_data="admin:users")
    kb.button(text="🔥 Топ запросов", callback_data="admin:top_queries")
    kb.button(text="❌ Закрыть", callback_data="delete:message")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def kb_admin_user_manage(user_id, is_banned, is_premium):
    kb = InlineKeyboardBuilder()
    ban_text = "🟢 Разбанить" if is_banned else "🔴 Забанить"
    ban_data = f"adm:unban:{user_id}" if is_banned else f"adm:ban:{user_id}"
    prem_text = "⬇️ Снять Premium" if is_premium else "⭐️ Дать Premium"
    prem_data = f"adm:unprem:{user_id}" if is_premium else f"adm:prem:{user_id}"
    kb.button(text=ban_text, callback_data=ban_data)
    kb.button(text=prem_text, callback_data=prem_data)
    kb.button(text="🔙 Назад", callback_data="admin:users")
    kb.adjust(1)
    return kb.as_markup()

def kb_admin_back():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin:main")]])

def kb_broadcast_actions():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить кнопку", callback_data="broadcast:add_btn")
    # 🔥 FIX: было "broadcast:confirm", а хендлер ловил "broadcast:send"
    kb.button(text="🚀 Отправить", callback_data="broadcast:send")
    kb.button(text="❌ Отмена", callback_data="broadcast:cancel")
    kb.adjust(1)
    return kb.as_markup()

def kb_profile(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_history'), callback_data="my:history")
    kb.button(text=T(uid, 'btn_playlists'), callback_data="open:playlists")
    kb.button(text=T(uid, 'btn_back'), callback_data="back:to:main")
    kb.adjust(1)
    return kb.as_markup()

def kb_history_back(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="my:profile")]])

def kb_lang(uid=None): 
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="set:lang:ru")
    kb.button(text="🇬🇧 English", callback_data="set:lang:en")
    kb.button(text="🇺🇦 Українська", callback_data="set:lang:ua")
    kb.button(text="🇰🇿 Қазақ тілі", callback_data="set:lang:kz")
    kb.button(text="🇺🇿 O'zbek tili", callback_data="set:lang:uz")
    kb.button(text="🇦🇪 العربية", callback_data="set:lang:ar")
    kb.adjust(2)
    if uid: kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="settings"))
    return kb.as_markup()

def kb_settings(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_lang'), callback_data="change:lang:menu")
    kb.button(text=T(uid, 'btn_del_acc'), callback_data="del:acc:ask")
    kb.button(text=T(uid, 'btn_back'), callback_data="back:to:main")
    kb.adjust(1)
    return kb.as_markup()

def kb_back_to_main(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="back:to:main")]])

def kb_auth(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_reg'), callback_data="auth:reg")
    kb.button(text=T(uid, 'btn_back'), callback_data="back:to:main") 
    kb.adjust(1)
    return kb.as_markup()

def kb_guest_confirm(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_go_reg'), callback_data="auth:reg")
    kb.button(text=T(uid, 'btn_sure_guest'), callback_data="confirm:guest")
    kb.adjust(1)
    return kb.as_markup()

def kb_genres(uid, selected_genres):
    kb = InlineKeyboardBuilder()
    for g in GENRES_LIST:
        text = f"✅ {g}" if g in selected_genres else g
        kb.button(text=text, callback_data=f"genre:{g}")
    kb.adjust(3)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_confirm'), callback_data="genre:done"))
    return kb.as_markup()

def kb_search(uid, results, page=0):
    return kb_back_to_main(uid)

def kb_cancel_search(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_cancel_search'), callback_data="back:to:main")
    return kb.as_markup()

def kb_playlist_options(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_rename_pl'), callback_data=f"setpl:name:{pl_name}")
    kb.button(text=T(uid, 'btn_icon_pl'), callback_data=f"setpl:icon:{pl_name}")
    kb.button(text=T(uid, 'btn_delete_pl'), callback_data=f"setpl:del:{pl_name}")
    kb.adjust(2, 1)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back_to_pl'), callback_data=f"viewpl:{pl_name}:0"))
    return kb.as_markup()

def kb_cancel_create(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_cancel_search'), callback_data="open:playlists")
    return kb.as_markup()

def kb_close(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_close'), callback_data="delete:message")]])

def kb_error_report(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text="🐞 Report Bug", callback_data="report:error")
    kb.button(text=T(uid, 'btn_back'), callback_data="delete:message")
    kb.adjust(1)
    return kb.as_markup()

def kb_cancel_ticket(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_cancel_ticket'), callback_data="ticket:cancel")]])

def kb_del_confirm(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_yes_del'), callback_data="del:acc:confirm")
    kb.button(text=T(uid, 'btn_back'), callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def kb_restore(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_restore'), callback_data="restore:acc")
    kb.button(text=T(uid, 'btn_guest'), callback_data="confirm:guest")
    kb.adjust(1)
    return kb.as_markup()

def kb_icon_select(uid, pl_name):
    kb = InlineKeyboardBuilder()
    icons = ["🔥", "💾", "🚗", "🏠", "💤", "🎉", "🎸", "🎤", "🏋️", "💔", "💿", "🌌"]
    for icon in icons:
        kb.button(text=icon, callback_data=f"doicon:{pl_name}:{icon}")
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data=f"pl:opts:{pl_name}"))
    return kb.as_markup()

def kb_pl_delete_confirm(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_yes_del'), callback_data=f"dodelpl:{pl_name}")
    kb.button(text=T(uid, 'btn_back'), callback_data=f"pl:opts:{pl_name}")
    kb.adjust(1)
    return kb.as_markup()

def kb_add_track_choice(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_from_fav'), callback_data=f"addtr:fav:{pl_name}")
    kb.button(text=T(uid, 'btn_search_new'), callback_data=f"addtr:search:{pl_name}")
    kb.button(text=T(uid, 'btn_back'), callback_data=f"viewpl:{pl_name}:0")
    kb.adjust(1)
    return kb.as_markup()

def kb_broadcast_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast:send"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel")
        ]
    ])

def kb_back_to_pl_view(uid, pl_name):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data=f"viewpl:{pl_name}:0")]])

def kb_back_to_pl(uid, pl_name):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data=f"viewpl:{pl_name}:0")]])