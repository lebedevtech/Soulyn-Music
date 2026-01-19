import os
import re
import yt_dlp
import asyncio
import time
import requests
import lyricsgenius
from concurrent.futures import ThreadPoolExecutor
from bot.config import PROXY_URL, COOKIES_PATH, USER_AGENT, GENIUS_TOKEN, BIN_DIR
from bot.loader import logger
from bot.utils import format_title, MusicSearcher, clean_string

# FFmpeg
ffmpeg_location = None
if os.path.exists(os.path.join(BIN_DIR, 'ffmpeg.exe')):
    ffmpeg_location = BIN_DIR

# --- НАСТРОЙКИ ЗАГРУЗЧИКА (TURBO NATIVE) ---
def get_ydl_opts():
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'source_address': '0.0.0.0',
        'ffmpeg_location': ffmpeg_location,
        
        # 🔥 ГЛАВНЫЕ УСКОРИТЕЛИ 🔥
        'concurrent_fragment_downloads': 5, # 5 нативных потоков (идеально для аудио)
        'force_ipv4': True,                 # Стабильнее, чем IPv6
        'buffersize': 1024 * 1024,          # Меньше обращений к диску
        
        # Тайм-ауты
        'socket_timeout': 10,
        
        # Фильтры
        'match_filter': yt_dlp.utils.match_filter_func("duration < 1200"),
        
        'retries': 5,
        'fragment_retries': 5,
        'skip_download': False,
        'postprocessor_args': {'ffmpeg': ['-metadata', 'comment=Downloaded via @SoulynMusicBot']}
    }
    
    if PROXY_URL: opts['proxy'] = PROXY_URL
    if COOKIES_PATH: opts['cookiefile'] = COOKIES_PATH
    if USER_AGENT: opts['user_agent'] = USER_AGENT
    
    return opts

executor = ThreadPoolExecutor(max_workers=10)

# --- GENIUS ---
try:
    genius = lyricsgenius.Genius(GENIUS_TOKEN, skip_non_songs=True, remove_section_headers=False, verbose=False)
except:
    genius = None

async def get_lyrics(artist, title):
    if not genius: return None
    clean_t = title.lower().replace(artist.lower(), "").strip()
    clean_t = clean_string(clean_t)
    try:
        loop = asyncio.get_event_loop()
        song = await loop.run_in_executor(None, lambda: genius.search_song(clean_t, artist))
        return song.lyrics if song else None
    except: return None

# --- ПОИСК ---
async def search_yt(query: str):
    loop = asyncio.get_event_loop()
    # 1. iTunes/Spotify
    music_results = await loop.run_in_executor(None, lambda: MusicSearcher.search_integrated(query))
    if music_results:
        clean_results = []
        for i, item in enumerate(music_results):
            clean_results.append({
                'id': f"{item['source']}:{item['id']}", 
                'title': item['display'],
                'uploader': item['source'].capitalize(), 
                'meta_pkg': item 
            })
        return clean_results
    # 2. Fallback
    return await _fallback_search(query)

async def _fallback_search(query):
    def run_search():
        opts = get_ydl_opts()
        opts['extract_flat'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"ytsearch20:{query}", download=False)

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, run_search)
        if not data or 'entries' not in data: return []
        
        clean_results = []
        seen = set()
        for entry in data['entries']:
            if not entry: continue
            title = entry.get('title', '')
            if len(title) < 2: continue
            if entry.get('duration', 0) > 1200: continue

            clean_t = format_title(title, entry.get('uploader', ''))
            if clean_t.lower() in seen: continue
            seen.add(clean_t.lower())
            
            clean_results.append({
                'id': entry.get('id'),
                'title': clean_t,
                'uploader': 'YouTube'
            })
        return clean_results
    except: return []

# --- РЕЗОЛВЕР ---
async def resolve_meta_to_youtube(artist, title):
    query = f"{artist} - {title} audio"
    def run_resolve():
        opts = get_ydl_opts()
        opts['extract_flat'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"ytsearch1:{query}", download=False)

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, run_resolve)
        if data and data['entries']:
            return data['entries'][0]['id']
    except: pass
    return None

# --- СКАЧИВАНИЕ ---
async def download_yt(vid, meta_pkg=None):
    real_vid = vid
    
    if meta_pkg and ":" in str(vid):
        real_vid = await resolve_meta_to_youtube(meta_pkg['artist'], meta_pkg['title'])
        if not real_vid: return None

    url = f"https://www.youtube.com/watch?v={real_vid}"
    
    def run_download():
        dl_opts = get_ydl_opts()
        dl_opts['postprocessors'] = [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
            {'key': 'EmbedThumbnail'},
            {'key': 'FFmpegMetadata', 'add_metadata': True}
        ]
        
        info = None
        current_filename = None
        
        # --- ПОПЫТКА 1 (Стандартная) ---
        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                current_filename = ydl.prepare_filename(info)
        except Exception as e:
            # --- ПОПЫТКА 2 (Retry с новым именем) ---
            print(f"⚠️ Retry (File Lock/Error): {e}")
            time.sleep(1.5)
            # Генерируем уникальное имя, чтобы обойти блокировку Windows
            dl_opts['outtmpl'] = 'downloads/%(id)s_retry_%(epoch)s.%(ext)s'
            
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                current_filename = ydl.prepare_filename(info)

        if not info: raise Exception("Extraction failed")

        if info.get('duration', 0) > 1200:
            if current_filename:
                base = current_filename.rsplit('.', 1)[0]
                for ext in ['.mp3', '.webm', '.m4a']:
                    if os.path.exists(base + ext): 
                        try: os.remove(base + ext)
                        except: pass
            raise Exception("Duration > 20 min")

        final_filename = current_filename.rsplit('.', 1)[0] + '.mp3'
        
        title = info.get('title')
        artist = info.get('uploader')
        album = info.get('album')
        genre = 'Music'
        cover_url = None
        
        if meta_pkg:
            title = meta_pkg['title']
            artist = meta_pkg['artist']
            album = meta_pkg['meta']['album']
            genre = meta_pkg['meta']['genre']
            cover_url = meta_pkg['meta']['cover']
        
        thumb_path = None
        if cover_url:
            try:
                thumb_path = f"{info['id']}.jpg"
                with open(thumb_path, 'wb') as f: f.write(requests.get(cover_url).content)
            except: pass
        elif info.get('thumbnail'):
            thumb_path = final_filename.replace(".mp3", ".jpg")
        
        return {
            'path': final_filename,
            'title': title,
            'artist': artist,
            'thumb_path': thumb_path,
            'meta': {'genre': genre, 'album': album}
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, run_download)