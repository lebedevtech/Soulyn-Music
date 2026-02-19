import aiosqlite
import json
import time
import datetime
import asyncio
from bot.config import SQLITE_DB_FILE
from bot.loader import logger, user_settings

class Database:
    @classmethod
    async def init_db(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            # 1. Таблица пользователей
            await db.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, status TEXT DEFAULT 'guest',
                lang TEXT DEFAULT 'ru', menu_id INTEGER, referrer_id INTEGER, nickname TEXT, join_date TEXT,
                last_active TEXT, downloads_today INTEGER DEFAULT 0, downloads_total INTEGER DEFAULT 0,
                fav_genres TEXT DEFAULT '{}', deleted_at REAL, is_banned INTEGER DEFAULT 0
            )''')
            
            # 2. Таблица треков (Кэш)
            await db.execute('''CREATE TABLE IF NOT EXISTS tracks (
                id TEXT PRIMARY KEY, file_id TEXT, title TEXT, artist TEXT, album TEXT, genre TEXT,
                year TEXT, cover TEXT, lyrics TEXT, is_explicit INTEGER DEFAULT 0, source_id TEXT,
                duration INTEGER DEFAULT 0, popularity INTEGER DEFAULT 0, meta TEXT, cached_at REAL
            )''')
            
            # 3. Плейлисты
            await db.execute('''CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, UNIQUE(user_id, name)
            )''')
            
            # 4. Треки в плейлистах
            await db.execute('''CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INTEGER, track_id TEXT, added_at REAL,
                FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, track_id)
            )''')

            # 5. История поиска
            await db.execute('''CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT, timestamp REAL
            )''')
            
            await db.commit()
            print("✅ Database initialized (Async Mode)")

    # --- ЗАГРУЗКА КЭША user_settings В RAM ---
    @classmethod
    async def load_user_settings_cache(cls):
        """Загружает lang и status всех юзеров в RAM при старте бота."""
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, lang, status FROM users") as cursor:
                async for row in cursor:
                    user_settings[row['id']] = {
                        'lang': row['lang'] or 'ru',
                        'status': row['status'] or 'guest'
                    }
        print(f"✅ Loaded {len(user_settings)} users into RAM cache")

    # --- ПОЛЬЗОВАТЕЛИ ---
    @classmethod
    async def get_user(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = dict(row)
                    # Подгружаем плейлисты пользователя сразу
                    async with db.execute("SELECT name, id FROM playlists WHERE user_id=?", (user_id,)) as pl_cursor:
                        playlists = {}
                        async for pl in pl_cursor:
                            async with db.execute("SELECT track_id FROM playlist_tracks WHERE playlist_id=?", (pl['id'],)) as t_cursor:
                                tracks = [t['track_id'] for t in await t_cursor.fetchall()]
                                playlists[pl['name']] = tracks
                        data['playlists'] = playlists
                    return data
                return None

    @classmethod
    async def register_user(cls, user_id, username, first_name, referrer_id=None):
        today = str(datetime.date.today())
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT id, lang FROM users WHERE id=?", (user_id,)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    await db.execute("UPDATE users SET username=?, full_name=?, last_active=? WHERE id=?", (username, first_name, today, user_id))
                else:
                    await db.execute('''INSERT INTO users (id, username, full_name, referrer_id, join_date, last_active, lang, status) 
                                 VALUES (?, ?, ?, ?, ?, ?, 'ru', 'guest')''', (user_id, username, first_name, referrer_id, today, today))
                    # Создаем дефолтный плейлист Избранное
                    await db.execute("INSERT OR IGNORE INTO playlists (user_id, name) VALUES (?, 'Favorites')", (user_id,))
                    # Обновляем RAM кэш
                    user_settings[user_id] = {'lang': 'ru', 'status': 'guest'}
            await db.commit()

    @classmethod
    async def set_lang(cls, user_id, lang_code):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET lang=? WHERE id=?", (lang_code, user_id))
            await db.commit()
        # 🔥 Обновляем RAM кэш
        if user_id not in user_settings:
            user_settings[user_id] = {}
        user_settings[user_id]['lang'] = lang_code

    @classmethod
    async def set_menu_id(cls, user_id, msg_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET menu_id=? WHERE id=?", (msg_id, user_id))
            await db.commit()

    @classmethod
    async def get_menu_id(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT menu_id FROM users WHERE id=?", (user_id,)) as cursor:
                res = await cursor.fetchone()
                return res[0] if res else None

    # --- ТРЕКИ ---
    @classmethod
    async def get_track(cls, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tracks WHERE id=?", (vid,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    d = dict(row)
                    try: d['meta'] = json.loads(d['meta'])
                    except: d['meta'] = {}
                    return d
                return None

    @classmethod
    async def cache_track(cls, vid, file_id, title, artist, meta=None, lyrics=None):
        meta_json = json.dumps(meta) if meta else '{}'
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('''INSERT INTO tracks 
                (id, file_id, title, artist, meta, lyrics, cached_at, popularity) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                file_id=excluded.file_id,
                popularity=tracks.popularity + 1
                ''', (vid, file_id, title, artist, meta_json, lyrics, time.time()))
            await db.commit()

    @classmethod
    async def increment_track_popularity(cls, vid):
        """Увеличивает счётчик популярности трека на 1."""
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE tracks SET popularity = popularity + 1 WHERE id=?", (vid,))
            await db.commit()

    @classmethod
    async def get_top_tracks(cls, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tracks WHERE popularity > 0 ORDER BY popularity DESC LIMIT ?", (limit,)) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    # --- ПЛЕЙЛИСТЫ ---
    @classmethod
    async def create_playlist(cls, user_id, title):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            try:
                await db.execute("INSERT INTO playlists (user_id, name) VALUES (?, ?)", (user_id, title))
                await db.commit()
                return True
            except: return False

    @classmethod
    async def rename_playlist(cls, user_id, old, new):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            try:
                await db.execute("UPDATE playlists SET name=? WHERE user_id=? AND name=?", (new, user_id, old))
                await db.commit()
                return True
            except: return False

    @classmethod
    async def delete_playlist(cls, user_id, name):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
             async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, name)) as c:
                res = await c.fetchone()
                if res:
                    await db.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (res[0],))
                    await db.execute("DELETE FROM playlists WHERE id=?", (res[0],))
                    await db.commit()

    @classmethod
    async def add_track_to_playlist(cls, user_id, playlist_name, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, playlist_name)) as c:
                res = await c.fetchone()
                if not res: return 
                pl_id = res[0]
            try:
                await db.execute("INSERT INTO playlist_tracks (playlist_id, track_id, added_at) VALUES (?, ?, ?)", (pl_id, vid, time.time()))
                await db.commit()
            except: pass 

    @classmethod
    async def remove_track_from_playlist(cls, user_id, playlist_name, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
             async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, playlist_name)) as c:
                res = await c.fetchone()
                if res:
                    await db.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (res[0], vid))
                    await db.commit()

    # --- ИСТОРИЯ И ПОИСК ---
    @classmethod
    async def add_search_history(cls, user_id, query):
        if len(query) < 2: return
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("INSERT INTO search_history (user_id, query, timestamp) VALUES (?, ?, ?)", 
                         (user_id, query[:100], time.time()))
            await db.commit()

    @classmethod
    async def get_user_history(cls, user_id, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT query FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)) as cursor:
                raw = [r[0] for r in await cursor.fetchall()]
                return list(dict.fromkeys(raw))
    
    @classmethod
    async def get_popular_searches(cls, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT query, count(*) as cnt FROM search_history GROUP BY query ORDER BY cnt DESC LIMIT ?", (limit,)) as c:
                return [(row[0], row[1]) for row in await c.fetchall()]

    # --- АДМИНКА И ПРОФИЛЬ ---
    @classmethod
    async def set_user_ban_status(cls, user_id, is_banned):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET is_banned=? WHERE id=?", (1 if is_banned else 0, user_id))
            await db.commit()

    @classmethod
    async def set_user_premium(cls, user_id, is_premium):
        status = 'premium' if is_premium else 'user'
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            await db.commit()
        # 🔥 Обновляем RAM кэш
        if user_id in user_settings:
            user_settings[user_id]['status'] = status
            
    @classmethod
    async def set_profile(cls, user_id, nickname, genres=None):
        g = json.dumps(genres) if genres else '{}'
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status='user', nickname=?, fav_genres=? WHERE id=?", (nickname, g, user_id))
            await db.commit()
        # 🔥 Обновляем RAM кэш
        if user_id in user_settings:
            user_settings[user_id]['status'] = 'user'
            
    @classmethod
    async def soft_delete_user(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status='guest' WHERE id=?", (user_id,))
            await db.commit()
        if user_id in user_settings:
            user_settings[user_id]['status'] = 'guest'
            
    @classmethod
    async def save_lyrics(cls, vid, text):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE tracks SET lyrics=? WHERE id=?", (text, vid))
            await db.commit()
            
    @classmethod
    async def check_limit(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT status, downloads_today, join_date, last_active FROM users WHERE id=?", (user_id,)) as c:
                row = await c.fetchone()
                if not row: return True
                
                today = str(datetime.date.today())
                if row['last_active'] != today:
                    await db.execute("UPDATE users SET last_active=?, downloads_today=0 WHERE id=?", (today, user_id))
                    await db.commit()
                    return True
                
                if row['status'] in ['user', 'premium', 'admin']: return True
                limit = 10 if row['join_date'] == today else 5
                return row['downloads_today'] < limit

    @classmethod
    async def update_stats(cls, user_id, genre=None):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET downloads_today = downloads_today + 1, downloads_total = downloads_total + 1 WHERE id=?", (user_id,))
            await db.commit()

    @classmethod
    async def get_stats(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as c:
                users = {r['id']: dict(r) for r in await c.fetchall()}
            async with db.execute("SELECT * FROM tracks") as c:
                tracks = {r['id']: dict(r) for r in await c.fetchall()}
            return users, tracks
            
    @classmethod
    async def get_daily_registrations(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            async with db.execute("SELECT join_date, count(*) as cnt FROM users GROUP BY join_date ORDER BY join_date DESC LIMIT 7") as c:
                return {row[0]: row[1] for row in await c.fetchall()}