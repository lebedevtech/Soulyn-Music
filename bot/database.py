import json
import os
import datetime
import time
from bot.config import DB_FILE, USERS_FILE
from bot.loader import logger

class Database:
    @staticmethod
    def _load(filename):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"DB Load Error {filename}: {e}")
                return {}
        return {}

    @staticmethod
    def _save(filename, data):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"DB Save Error {filename}: {e}")

    @classmethod
    def register_user(cls, user_id, username, first_name):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        today = str(datetime.date.today())
        
        if uid not in users:
            users[uid] = {
                "username": username,
                "tg_name": first_name,
                "status": "guest",
                "lang": None,
                "menu_id": None, # НОВОЕ ПОЛЕ ДЛЯ ID МЕНЮ
                "nickname": None,
                "join_date": today,
                "last_active": today,
                "downloads_today": 0,
                "downloads_total": 0,
                "fav_genres": {},
                "explicit_genres": [],
                "playlists": {"Favorites": []} 
            }
            cls._save(USERS_FILE, users)
        else:
            if users[uid].get("username") != username:
                users[uid]["username"] = username
                cls._save(USERS_FILE, users)

    # --- УПРАВЛЕНИЕ ID МЕНЮ (ЧТОБЫ НЕ БЫЛО ДУБЛЕЙ) ---
    @classmethod
    def set_menu_id(cls, user_id, msg_id):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            users[uid]["menu_id"] = msg_id
            cls._save(USERS_FILE, users)

    @classmethod
    def get_menu_id(cls, user_id):
        users = cls._load(USERS_FILE)
        return users.get(str(user_id), {}).get("menu_id")

    @classmethod
    def set_lang(cls, user_id, lang_code):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            users[uid]["lang"] = lang_code
            cls._save(USERS_FILE, users)

    @classmethod
    def get_user(cls, user_id):
        return cls._load(USERS_FILE).get(str(user_id))

    @classmethod
    def set_profile(cls, user_id, nickname, genres=None):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            users[uid]["status"] = "user"
            users[uid]["nickname"] = nickname
            if genres: 
                users[uid]["explicit_genres"] = genres
            if "Favorites" not in users[uid].get("playlists", {}):
                users[uid].setdefault("playlists", {})["Favorites"] = []
            cls._save(USERS_FILE, users)

    @classmethod
    def restore_user(cls, user_id):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users and "deleted_at" in users[uid]:
            users[uid]["status"] = "user"
            del users[uid]["deleted_at"]
            cls._save(USERS_FILE, users)
            return True
        return False
    
    @classmethod
    def soft_delete_user(cls, user_id):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            users[uid]["status"] = "guest"
            users[uid]["deleted_at"] = time.time()
            cls._save(USERS_FILE, users)

    @classmethod
    def check_limit(cls, user_id):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid not in users: return True
        user = users[uid]
        today = str(datetime.date.today())
        
        if user.get("last_active") != today:
            user["last_active"] = today
            user["downloads_today"] = 0
            cls._save(USERS_FILE, users) 
        
        if user.get("status") == "user": return True
        
        cnt = user.get("downloads_today", 0)
        join_date = user.get("join_date", today)
        limit = 10 if join_date == today else 5
        return cnt < limit

    @classmethod
    def update_stats(cls, user_id, genre=None):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            if "downloads_total" not in users[uid]: users[uid]["downloads_total"] = 0
            if "downloads_today" not in users[uid]: users[uid]["downloads_today"] = 0
            
            users[uid]["downloads_total"] += 1
            users[uid]["downloads_today"] += 1
            
            if genre and genre != "Unknown":
                simple_genre = genre.split("/")[0].split(",")[0].strip()
                if "fav_genres" not in users[uid]: users[uid]["fav_genres"] = {}
                users[uid]["fav_genres"][simple_genre] = users[uid]["fav_genres"].get(simple_genre, 0) + 1
            
            cls._save(USERS_FILE, users)

    # --- PLAYLISTS ---
    @classmethod
    def create_playlist(cls, user_id, title):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            if title not in users[uid]["playlists"]:
                users[uid]["playlists"][title] = []
                cls._save(USERS_FILE, users)
                return True
        return False

    @classmethod
    def rename_playlist(cls, user_id, old_name, new_name):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users and old_name in users[uid]["playlists"]:
            if new_name in users[uid]["playlists"]: return False
            tracks = users[uid]["playlists"].pop(old_name)
            users[uid]["playlists"][new_name] = tracks
            cls._save(USERS_FILE, users)
            return True
        return False

    @classmethod
    def delete_playlist(cls, user_id, name):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users and name in users[uid]["playlists"]:
            del users[uid]["playlists"][name]
            cls._save(USERS_FILE, users)
            return True
        return False

    @classmethod
    def add_track_to_playlist(cls, user_id, playlist_name, vid):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users:
            if "playlists" not in users[uid]: users[uid]["playlists"] = {}
            if playlist_name == "Favorites" and "Favorites" not in users[uid]["playlists"]:
                users[uid]["playlists"]["Favorites"] = []
                
            if playlist_name in users[uid]["playlists"]:
                if vid not in users[uid]["playlists"][playlist_name]:
                    users[uid]["playlists"][playlist_name].append(vid)
                    cls._save(USERS_FILE, users)
                    return "added"
                return "exists"
        return "error"

    @classmethod
    def remove_track_from_playlist(cls, user_id, playlist_name, vid):
        users = cls._load(USERS_FILE)
        uid = str(user_id)
        if uid in users and playlist_name in users[uid]["playlists"]:
            if vid in users[uid]["playlists"][playlist_name]:
                users[uid]["playlists"][playlist_name].remove(vid)
                cls._save(USERS_FILE, users)
                return True
        return False

    @classmethod
    def migrate_db(cls):
        users = cls._load(USERS_FILE)
        changed = False
        today = str(datetime.date.today())
        
        logger.info("Checking database consistency...")
        
        for uid, user in users.items():
            if "menu_id" not in user: user["menu_id"] = None; changed = True # MIGRATION
            if "lang" not in user: user["lang"] = None; changed = True
            
            if "downloads" in user:
                current_total = user.get("downloads_total", 0)
                user["downloads_total"] = current_total + user["downloads"]
                del user["downloads"]
                changed = True
            
            if "downloads_total" not in user: user["downloads_total"] = 0; changed = True
            if "downloads_today" not in user: user["downloads_today"] = 0; changed = True
            if "playlists" not in user: user["playlists"] = {"Favorites": []}; changed = True
            elif "Favorites" not in user["playlists"]: user["playlists"]["Favorites"] = []; changed = True
            if "fav_genres" not in user: user["fav_genres"] = {}; changed = True
            if "status" not in user: user["status"] = "guest"; changed = True
            if "join_date" not in user: user["join_date"] = today; changed = True

        if changed:
            cls._save(USERS_FILE, users)
            logger.info("✅ Database migrated.")
        else:
            logger.info("✅ Database clean.")

    @classmethod
    def cache_track(cls, vid, file_id, title, artist, meta=None):
        db = cls._load(DB_FILE)
        track_data = {"file_id": file_id, "title": title, "artist": artist, "date": time.time()}
        if meta: track_data.update(meta)
        db[vid] = track_data
        cls._save(DB_FILE, db)

    @classmethod
    def get_track(cls, vid):
        return cls._load(DB_FILE).get(vid)

    @classmethod
    def get_stats(cls):
        return cls._load(USERS_FILE), cls._load(DB_FILE)