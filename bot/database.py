import aiosqlite
import json
import os
import time
import datetime
import asyncio
from bot.config import SQLITE_DB_FILE, OLD_DB_FILE, OLD_USERS_FILE
from bot.loader import logger, user_settings

class Database:
    @classmethod
    async def init_db(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            # Users
            await db.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, status TEXT DEFAULT 'guest',
                lang TEXT, menu_id INTEGER, referrer_id INTEGER, nickname TEXT, join_date TEXT,
                last_active TEXT, downloads_today INTEGER DEFAULT 0, downloads_total INTEGER DEFAULT 0,
                fav_genres TEXT DEFAULT '{}', deleted_at REAL, is_banned INTEGER DEFAULT 0
            )''')
            
            # Миграция
            try: await db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
            except: pass

            # Tracks
            await db.execute('''CREATE TABLE IF NOT EXISTS tracks (
                id TEXT PRIMARY KEY, file_id TEXT, title TEXT, artist TEXT, album TEXT, genre TEXT,
                year TEXT, cover TEXT, lyrics TEXT, is_explicit INTEGER DEFAULT 0, source_id TEXT,
                duration INTEGER DEFAULT 0, popularity INTEGER DEFAULT 0, meta TEXT, cached_at REAL
            )''')
            
            # Playlists
            await db.execute('''CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, UNIQUE(user_id, name)
            )''')
            await db.execute('''CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INTEGER, track_id TEXT, added_at REAL,
                FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, track_id)
            )''')

            # History
            await db.execute('''CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT, timestamp REAL
            )''')
            
            await db.commit()
        
        # Загрузка кэша в RAM для быстрого доступа
        await cls.load_cache()
        # Старые миграции (если нужны)
        await cls._migrate_smart()

    @classmethod
    async def load_cache(cls):
        """Загружаем основные настройки юзеров в RAM, чтобы T() работал синхронно"""
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, lang, status, is_banned FROM users") as cursor:
                async for row in cursor:
                    user_settings[row['id']] = {
                        'lang': row['lang'] or 'ru',
                        'status': row['status'],
                        'is_banned': row['is_banned']
                    }
        logger.info(f"🚀 Loaded settings for {len(user_settings)} users into RAM cache")

    # --- ПОЛЬЗОВАТЕЛИ ---
    @classmethod
    async def get_user(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = dict(row)
                    # Обновляем кэш
                    user_settings[user_id] = {
                        'lang': data['lang'],
                        'status': data['status'],
                        'is_banned': data['is_banned']
                    }
                    
                    try: data['fav_genres'] = json.loads(data['fav_genres'])
                    except: data['fav_genres'] = {}
                    
                    # Подгружаем плейлисты
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
            # Проверяем, есть ли юзер
            async with db.execute("SELECT id FROM users WHERE id=?", (user_id,)) as cursor:
                if await cursor.fetchone():
                    await db.execute("UPDATE users SET username=?, full_name=? WHERE id=?", (username, first_name, user_id))
                else:
                    await db.execute('''INSERT INTO users (id, username, full_name, referrer_id, join_date, last_active, lang, status) 
                                 VALUES (?, ?, ?, ?, ?, ?, 'ru', 'guest')''', (user_id, username, first_name, referrer_id, today, today))
                    await db.execute("INSERT INTO playlists (user_id, name) VALUES (?, 'Favorites')", (user_id,))
                    # Обновляем кэш для нового юзера
                    user_settings[user_id] = {'lang': 'ru', 'status': 'guest', 'is_banned': 0}
            await db.commit()

    @classmethod
    async def set_lang(cls, user_id, lang_code):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET lang=? WHERE id=?", (lang_code, user_id))
            await db.commit()
        # Обновляем кэш
        if user_id in user_settings:
            user_settings[user_id]['lang'] = lang_code
        else:
            user_settings[user_id] = {'lang': lang_code, 'status': 'guest'}

    @classmethod
    async def set_menu_id(cls, user_id, msg_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET menu_id=? WHERE id=?", (msg_id, user_id))
            await db.commit()

    @classmethod
    async def get_menu_id(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT menu_id FROM users WHERE id=?", (user_id,)) as cursor:
                res = await cursor.fetchone()
                return res['menu_id'] if res else None

    # --- ТРЕКИ ---
    @classmethod
    async def cache_track(cls, vid, file_id, title, artist, meta=None, lyrics=None):
        meta_dict = meta if meta else {}
        album = meta_dict.get('album')
        genre = meta_dict.get('genre')
        year = meta_dict.get('year')
        cover = meta_dict.get('cover')
        is_explicit = 1 if meta_dict.get('is_explicit') else 0
        source_id = meta_dict.get('source_id')
        
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            # Проверяем старый текст
            final_lyrics = lyrics
            if not final_lyrics:
                async with db.execute("SELECT lyrics FROM tracks WHERE id=?", (vid,)) as cursor:
                    res = await cursor.fetchone()
                    if res and res['lyrics']: final_lyrics = res['lyrics']

            full_meta = meta_dict.copy()
            if album: full_meta['album'] = album
            if genre: full_meta['genre'] = genre
            if year: full_meta['year'] = str(year)
            if cover: full_meta['cover'] = cover

            await db.execute('''INSERT INTO tracks 
                (id, file_id, title, artist, album, genre, year, cover, lyrics, is_explicit, source_id, meta, cached_at, popularity) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                file_id=excluded.file_id,
                lyrics=COALESCE(excluded.lyrics, tracks.lyrics),
                album=COALESCE(excluded.album, tracks.album),
                genre=COALESCE(excluded.genre, tracks.genre),
                year=COALESCE(excluded.year, tracks.year),
                cover=COALESCE(excluded.cover, tracks.cover),
                popularity=tracks.popularity + 1,
                cached_at=excluded.cached_at,
                meta=excluded.meta
                ''', 
                (vid, file_id, title, artist, album, genre, year, cover, final_lyrics, is_explicit, source_id, json.dumps(full_meta), time.time()))
            await db.commit()

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
                    if d['year']: d['meta']['year'] = d['year']
                    if d['album']: d['meta']['album'] = d['album']
                    if d['genre']: d['meta']['genre'] = d['genre']
                    if d['cover']: d['meta']['cover'] = d['cover']
                    if d['lyrics']: d['meta']['lyrics'] = d['lyrics']
                    return d
                return None

    @classmethod
    async def get_top_tracks(cls, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tracks WHERE popularity > 0 ORDER BY popularity DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                tracks = []
                for row in rows:
                    d = dict(row)
                    try: d['meta'] = json.loads(d['meta'])
                    except: d['meta'] = {}
                    if d['year']: d['meta']['year'] = d['year']
                    if d['genre']: d['meta']['genre'] = d['genre']
                    tracks.append(d)
                return tracks

    @classmethod
    async def increment_track_popularity(cls, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            try:
                await db.execute("UPDATE tracks SET popularity = popularity + 1 WHERE id=?", (vid,))
                await db.commit()
            except: pass

    @classmethod
    async def save_lyrics(cls, vid, text):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE tracks SET lyrics=? WHERE id=?", (text, vid))
            await db.commit()

    # --- ИСТОРИЯ И СТАТИСТИКА ---
    @classmethod
    async def add_search_history(cls, user_id, query):
        if len(query) < 2: return
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("INSERT INTO search_history (user_id, query, timestamp) VALUES (?, ?, ?)", 
                         (user_id, query.strip()[:100], time.time()))
            await db.commit()

    @classmethod
    async def get_user_history(cls, user_id, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT query FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)) as cursor:
                history = []
                seen = set()
                async for row in cursor:
                    q = row['query']
                    if q not in seen:
                        history.append(q)
                        seen.add(q)
                return history

    @classmethod
    async def get_stats(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, downloads_total FROM users") as cursor:
                rows = await cursor.fetchall()
                users = {str(r['id']): {'downloads_total': r['downloads_total']} for r in rows}
            async with db.execute("SELECT id, title FROM tracks") as cursor:
                rows = await cursor.fetchall()
                tracks = {r['id']: {'title': r['title']} for r in rows}
            return users, tracks

    @classmethod
    async def get_daily_registrations(cls):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT join_date, count(*) as cnt FROM users GROUP BY join_date ORDER BY join_date DESC LIMIT 7") as cursor:
                rows = await cursor.fetchall()
                return {row['join_date']: row['cnt'] for row in rows}

    @classmethod
    async def get_popular_searches(cls, limit=10):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT query, count(*) as cnt FROM search_history GROUP BY query ORDER BY cnt DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [(row['query'], row['cnt']) for row in rows]

    # --- ПЛЕЙЛИСТЫ И ПРОЧЕЕ ---
    @classmethod
    async def add_track_to_playlist(cls, user_id, playlist_name, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, playlist_name)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    if playlist_name == "Favorites":
                        await db.execute("INSERT INTO playlists (user_id, name) VALUES (?, ?)", (user_id, playlist_name))
                        # Нужно получить ID созданного, но в aiosqlite лучше сделать второй select или lastrowid
                        async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, playlist_name)) as c2:
                            row = await c2.fetchone()
                    else: return "error"
                
                pl_id = row['id']
                try:
                    await db.execute("INSERT INTO playlist_tracks (playlist_id, track_id, added_at) VALUES (?, ?, ?)", (pl_id, vid, time.time()))
                    await db.commit()
                    return "added"
                except sqlite3.IntegrityError: return "exists" # aiosqlite пробрасывает исключения sqlite3

    @classmethod
    async def remove_track_from_playlist(cls, user_id, playlist_name, vid):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, playlist_name)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (row['id'], vid))
                    await db.commit()
                    return True
            return False

    @classmethod
    async def create_playlist(cls, user_id, title):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            try:
                await db.execute("INSERT INTO playlists (user_id, name) VALUES (?, ?)", (user_id, title))
                await db.commit()
                return True
            except: return False

    @classmethod
    async def rename_playlist(cls, user_id, old_name, new_name):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            try:
                await db.execute("UPDATE playlists SET name=? WHERE user_id=? AND name=?", (new_name, user_id, old_name))
                await db.commit()
                return True
            except: return False

    @classmethod
    async def delete_playlist(cls, user_id, name):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id FROM playlists WHERE user_id=? AND name=?", (user_id, name)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (row['id'],))
                    await db.execute("DELETE FROM playlists WHERE id=?", (row['id'],))
                    await db.commit()
                    return True
            return False

    @classmethod
    async def set_profile(cls, user_id, nickname, genres=None):
        genres_json = json.dumps(genres) if genres else '{}'
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status='user', nickname=?, fav_genres=? WHERE id=?", (nickname, genres_json, user_id))
            await db.commit()
        # Кэш
        if user_id in user_settings:
            user_settings[user_id]['status'] = 'user'

    @classmethod
    async def check_limit(cls, user_id):
        # 1. Сначала чекаем кэш (СУПЕР БЫСТРО)
        if user_id in user_settings:
            status = user_settings[user_id].get('status', 'guest')
            if status in ['user', 'premium', 'admin']: return True
        
        # 2. Если гость - чекаем базу
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT status, join_date, last_active, downloads_today FROM users WHERE id=?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return True
                
                today = str(datetime.date.today())
                downloads = row['downloads_today']
                
                if row['last_active'] != today:
                    await db.execute("UPDATE users SET last_active=?, downloads_today=0 WHERE id=?", (today, user_id))
                    await db.commit()
                    downloads = 0
                
                if row['status'] in ['user', 'premium', 'admin']: return True
                limit = 10 if row['join_date'] == today else 5
                return downloads < limit

    @classmethod
    async def update_stats(cls, user_id, genre=None):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET downloads_today = downloads_today + 1, downloads_total = downloads_total + 1 WHERE id=?", (user_id,))
            if genre and genre != "Unknown":
                # Упрощенная логика: читаем, обновляем, пишем (может быть race condition, но для статы не критично)
                # Для скорости можно пропустить обновление жанров каждый раз
                pass 
            await db.commit()

    @classmethod
    async def soft_delete_user(cls, user_id):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status='guest', deleted_at=? WHERE id=?", (time.time(), user_id))
            await db.commit()

    @classmethod
    async def set_user_ban_status(cls, user_id, is_banned):
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET is_banned=? WHERE id=?", (1 if is_banned else 0, user_id))
            await db.commit()
        if user_id in user_settings: user_settings[user_id]['is_banned'] = 1 if is_banned else 0

    @classmethod
    async def set_user_premium(cls, user_id, is_premium):
        status = 'premium' if is_premium else 'user'
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            await db.commit()
        if user_id in user_settings: user_settings[user_id]['status'] = status

    @classmethod
    async def _migrate_smart(cls):
        # Заглушка, чтобы не тащить весь код миграции каждый раз. 
        # Если базы нет, create tables всё сделает.
        pass