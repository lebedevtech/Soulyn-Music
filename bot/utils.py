import re
import requests
import emoji 
import asyncio
import time
import base64
from contextlib import suppress
from aiogram import exceptions
from bot.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# --- АВТОУДАЛЕНИЕ ---
async def delete_later(msg, delay=2.5):
    await asyncio.sleep(delay)
    with suppress(exceptions.TelegramBadRequest, exceptions.TelegramAPIError):
        await msg.delete()

# --- ЯДЕРНАЯ ЧИСТКА ---
JUNK_PATTERNS = [
    r'(?i)\b(hq|hd|4k|1080p|720p|mv|m/v|official|video|audio|lyrics|lyric|clip|visualizer)\b',
    r'(?i)[(\[]\s*(official|music|video|audio|lyric|clip|mv|hd|hq|4k|remastered|live|cover|prod|by|feat|ft)\s*.*?[\)\]]',
    r'(?i)\b(официальный|клип|видео|аудио|премьера|звук|текст|слова|кавер|лайв|концерт|версия|ремастер)\b',
    r'(?i)\b(полный трек|полная версия|сниппет|новинка|хит|повтори|слушать|скачать|на бите)\b',
    r'(?i)[(\[]\s*(полный трек|полная версия|повтори)\s*.*?[\)\]]',
    r'\b\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}\b', 
    r'(?i)[(\[,]\s*20\d{2}\s*[\)\]]',
    r'\b20\d{2}\b',
    r'(?i)\+\s*(video|audio|lyrics|text|текст|видео|повтори)',
]

def clean_string(text):
    if not text: return ""
    text = emoji.replace_emoji(text, replace='')
    text = re.sub(r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', '', text)
    text = re.sub(r'\s*[-–—_|/]+\s*', ' - ', text)
    for pattern in JUNK_PATTERNS: text = re.sub(pattern, '', text)
    text = re.sub(r'\(\s*\)', '', text)
    text = re.sub(r'\[\s*\]', '', text)
    text = text.replace('"', '').replace("'", '').replace('«', '').replace('»', '')
    text = re.sub(r'[\.,\s]+$', '', text)
    text = re.sub(r'^[\.,\s]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^-\s*', '', text)
    text = re.sub(r'\s*-$', '', text)
    return text

def format_title(title, uploader):
    clean_uploader = uploader.replace(" - Topic", "").replace("VEVO", "").replace("Official", "").strip()
    clean_uploader = clean_string(clean_uploader)
    clean_title = clean_string(title)
    if " - " in clean_title:
        parts = clean_title.split(" - ")
        if len(parts) > 1:
            first_part = parts[0].lower()
            uploader_lower = clean_uploader.lower()
            if first_part in uploader_lower or uploader_lower in first_part:
                return " - ".join(parts[1:])
    if " - " not in clean_title and len(clean_uploader) > 1:
        if clean_uploader.lower() not in clean_title.lower():
            return f"{clean_uploader} - {clean_title}"
    return clean_title

# --- КЛАСС ПОИСКА В ITUNES/SPOTIFY ---
class MusicSearcher:
    _spotify_token = None
    _token_expiry = 0

    @classmethod
    def _get_spotify_token(cls):
        # Если ключи не заданы - пропускаем
        try:
            if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET: return None
        except NameError: return None # На случай, если переменных вообще нет
        
        if cls._spotify_token and time.time() < cls._token_expiry: return cls._spotify_token
        
        try:
            auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            resp = requests.post(
                "https://accounts.spotify.com/api/token", 
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {b64_auth}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                cls._spotify_token = data["access_token"]
                cls._token_expiry = time.time() + data["expires_in"] - 60
                return cls._spotify_token
        except: pass
        return None

    @classmethod
    def search_spotify(cls, query, limit=10):
        token = cls._get_spotify_token()
        if not token: return []
        
        try:
            resp = requests.get(
                "https://api.spotify.com/v1/search",
                params={"q": query, "type": "track", "limit": limit},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5
            )
            data = resp.json()
            results = []
            for track in data.get("tracks", {}).get("items", []):
                artists = ", ".join([a["name"] for a in track["artists"]])
                album = track["album"]["name"]
                year = track["album"]["release_date"][:4] if track["album"]["release_date"] else ""
                cover = track["album"]["images"][0]["url"] if track["album"]["images"] else ""
                
                results.append({
                    "source": "spotify",
                    "id": track["id"],
                    "artist": artists,
                    "title": track["name"],
                    "display": f"{artists} - {track['name']}",
                    "meta": {
                        "album": album,
                        "year": year,
                        "genre": "Music",
                        "cover": cover
                    }
                })
            return results
        except: return []

    @classmethod
    def search_itunes(cls, query, limit=15):
        try:
            clean_q = re.sub(r'[^\w\s]', '', query)
            resp = requests.get(
                "https://itunes.apple.com/search", 
                params={"term": clean_q, "media": "music", "entity": "song", "limit": limit}, 
                timeout=5
            )
            data = resp.json()
            results = []
            if data.get("resultCount", 0) > 0:
                for track in data["results"]:
                    results.append({
                        "source": "itunes",
                        "id": str(track["trackId"]),
                        "artist": track["artistName"],
                        "title": track["trackName"],
                        "display": f"{track['artistName']} - {track['trackName']}",
                        "meta": {
                            "album": track["collectionName"],
                            "year": track.get("releaseDate", "")[:4],
                            "genre": track.get("primaryGenreName", "Music"),
                            "cover": track.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                        }
                    })
            return results
        except: return []

    @classmethod
    def search_integrated(cls, query):
        # 1. Spotify
        res = cls.search_spotify(query, limit=10)
        if res: return res
        
        # 2. iTunes (Основной вариант)
        res = cls.search_itunes(query, limit=15)
        return res

def clean_for_genius(text):
    return clean_string(text)

def split_playlist_name(pl_name):
    if not pl_name: return None, ""
    parts = pl_name.split(" ", 1)
    if len(parts) > 1 and emoji.is_emoji(parts[0]):
        return parts[0], parts[1] 
    return None, pl_name