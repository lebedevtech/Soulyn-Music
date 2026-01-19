import math
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from bot.texts import T
from bot.config import SUPPORT_LINK, CHANNEL_LINK, GENRES_LIST
from bot.utils import format_title, split_playlist_name
from bot.database import Database

# --- ВЫБОР ЯЗЫКА (6 ЯЗЫКОВ) ---
def kb_lang():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="set:lang:ru")
    kb.button(text="🇬🇧 English", callback_data="set:lang:en")
    kb.button(text="🇺🇦 Українська", callback_data="set:lang:ua")
    kb.button(text="🇰🇿 Қазақ тілі", callback_data="set:lang:kz")
    kb.button(text="🇺🇿 O'zbek tili", callback_data="set:lang:uz")
    kb.button(text="🇦🇪 العربية", callback_data="set:lang:ar")
    kb.adjust(2)
    return kb.as_markup()

# --- ГЛАВНОЕ МЕНЮ ---
def kb_menu(uid):
    kb = InlineKeyboardBuilder()
    user = Database.get_user(uid)
    kb.button(text=T(uid, 'btn_search_main'), callback_data="nav:search")
    kb.button(text=T(uid, 'btn_fav_icon'), callback_data="viewpl:Favorites:0") 
    kb.button(text=T(uid, 'btn_open_pl'), callback_data="open:playlists")
    
    if user and user.get("status") == "user":
        kb.button(text=T(uid, 'btn_profile_short'), callback_data="my:profile")
    else:
        kb.button(text=T(uid, 'btn_reg'), callback_data="auth:reg")
    
    kb.button(text=T(uid, 'btn_set'), callback_data="settings")
    kb.adjust(1, 2, 2) 
    return kb.as_markup()

# --- АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ---
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

# --- ПОИСК ---
def kb_search(uid, results, page=0):
    if not results: return None
    total = math.ceil(len(results) / 5)
    start, end = page * 5, (page + 1) * 5
    kb = InlineKeyboardBuilder()
    for res in results[start:end]:
        title = format_title(res.get('title'), res.get('uploader'))
        if len(title) > 40: title = title[:37] + "..."
        kb.button(text=f"🎵 {title}", callback_data=f"dl:{res['id']}")
    kb.adjust(1)
    row = []
    if page > 0: row.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{page-1}"))
    row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total}", callback_data="ignore"))
    if page < total - 1: row.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{page+1}"))
    kb.row(*row)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="delete:search"))
    return kb.as_markup()

def kb_cancel_search(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_cancel_search'), callback_data="back:to:main")
    return kb.as_markup()

# --- ПЛЕЙЛИСТЫ ---
def kb_all_playlists(uid):
    user = Database.get_user(uid)
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

def kb_playlist_view(uid, tracks, page=0, pl_name="Favorites"):
    kb = InlineKeyboardBuilder()
    if tracks:
        total = math.ceil(len(tracks) / 5)
        start, end = page * 5, (page + 1) * 5
        for vid in tracks[start:end]:
            info = Database.get_track(vid)
            if info:
                title = format_title(info.get('title'), info.get('artist'))
                if len(title) > 35: title = title[:32] + "..."
                kb.button(text=f"🎵 {title}", callback_data=f"dl:{vid}:{pl_name}")
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
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_open_pl'), callback_data="open:playlists"))
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data="back:to:main"))
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

def kb_back_to_pl_view(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_back_to_pl'), callback_data=f"viewpl:{pl_name}:0")
    return kb.as_markup()

def kb_back_to_pl(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_back'), callback_data=f"viewpl:{pl_name}:0")
    return kb.as_markup()

# --- УПРАВЛЕНИЕ ТРЕКОМ ---
def kb_track(uid, vid, from_playlist=None, is_liked=False):
    kb = InlineKeyboardBuilder()
    if from_playlist != "Favorites":
        kb.button(text="💔" if is_liked else "❤️", callback_data=f"{'unfav' if is_liked else 'fav'}:{vid}")
    kb.button(text=T(uid, 'btn_lyrics_short'), callback_data=f"lyrics:{vid}")
    
    user = Database.get_user(uid)
    if user and user.get("status") == "user":
        if from_playlist:
            kb.button(text=T(uid, 'btn_remove_track'), callback_data=f"rmtr:{from_playlist}:{vid}")
            kb.button(text=T(uid, 'btn_move_track'), callback_data=f"movetr:ask:{vid}:{from_playlist}")
            kb.adjust(1, 2) if from_playlist == "Favorites" else kb.adjust(2, 2)
        else:
            kb.button(text=T(uid, 'add_to_pl'), callback_data=f"addpl:{vid}")
            kb.adjust(2, 1)
    else:
        kb.adjust(2)
    return kb.as_markup()

# --- ПРОФИЛЬ И НАСТРОЙКИ ---
def kb_profile(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_open_pl'), callback_data="open:playlists")
    kb.button(text=T(uid, 'btn_back'), callback_data="back:to:main")
    kb.adjust(1)
    return kb.as_markup()

def kb_settings(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_lang'), callback_data="change:lang:menu")
    kb.button(text=T(uid, 'btn_support'), callback_data="open:ticket") 
    kb.button(text=T(uid, 'btn_channel'), url=CHANNEL_LINK)
    kb.button(text=T(uid, 'btn_back'), callback_data="back:to:main")
    kb.adjust(1, 2, 1)
    return kb.as_markup()

# --- ВСПОМОГАТЕЛЬНЫЕ ---
def kb_close(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_close'), callback_data="delete:message")
    return kb.as_markup()

def kb_ok(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_ok'), callback_data="delete:message")
    return kb.as_markup()

def kb_error_report(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text="🐞 Report Bug", callback_data="report:error")
    kb.button(text=T(uid, 'btn_back'), callback_data="delete:message")
    kb.adjust(1)
    return kb.as_markup()

def kb_cancel_ticket(uid):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_cancel_ticket'), callback_data="ticket:cancel")
    return kb.as_markup()

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

# --- ПЛЕЙЛИСТЫ (ВЫБОР, ИКОНКИ, ПЕРЕМЕЩЕНИЕ) ---
def kb_select_playlist(uid, vid):
    user = Database.get_user(uid)
    kb = InlineKeyboardBuilder()
    if user and user.get("playlists"):
        for pl_name in user["playlists"]:
            if pl_name == "Favorites":
                label = T(uid, 'btn_fav_icon')
            else:
                icon, clean_name = split_playlist_name(pl_name)
                label = f"{icon} {clean_name}" if icon else f"📂 {clean_name}"
            kb.button(text=label, callback_data=f"savepl:{vid}:{pl_name}")
    kb.button(text=T(uid, 'pl_create'), callback_data="create:playlist")
    kb.button(text=T(uid, 'btn_close'), callback_data="delete:message")
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

def kb_move_target(uid, vid, from_pl):
    user = Database.get_user(uid)
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

def kb_add_track_choice(uid, pl_name):
    kb = InlineKeyboardBuilder()
    kb.button(text=T(uid, 'btn_from_fav'), callback_data=f"addtr:fav:{pl_name}")
    kb.button(text=T(uid, 'btn_search_new'), callback_data=f"addtr:search:{pl_name}")
    kb.button(text=T(uid, 'btn_back'), callback_data=f"viewpl:{pl_name}:0")
    kb.adjust(1)
    return kb.as_markup()

def kb_select_from_fav(uid, target_pl, page=0):
    user = Database.get_user(uid)
    tracks = user.get("playlists", {}).get("Favorites", [])
    if not tracks: return None
    total = math.ceil(len(tracks) / 5)
    start, end = page * 5, (page + 1) * 5
    kb = InlineKeyboardBuilder()
    for vid in tracks[start:end]:
        info = Database.get_track(vid)
        if info:
            title = format_title(info.get('title'), info.get('artist'))
            if len(title) > 40: title = title[:37] + "..."
            kb.button(text=f"➕ {title}", callback_data=f"addtr:save:{vid}:{target_pl}")
    kb.adjust(1)
    row = []
    if page > 0: row.append(InlineKeyboardButton(text="⬅️", callback_data=f"addtr:fav:{target_pl}:{page-1}"))
    row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total}", callback_data="ignore"))
    if page < total - 1: row.append(InlineKeyboardButton(text="➡️", callback_data=f"addtr:fav:{target_pl}:{page+1}"))
    kb.row(*row)
    kb.row(InlineKeyboardButton(text=T(uid, 'btn_back'), callback_data=f"addtr:menu:{target_pl}"))
    return kb.as_markup()