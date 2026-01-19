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
        'concurrent_fragment_downloads': 5,
        'force_ipv4': True,
        'buffersize': 1024 * 1024,
        'socket_timeout': 10,
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
    music_results = await loop.run_in_executor(None, lambda: MusicSearcher.search_integrated(query))
    if music_results:
        clean_results = []
        for item in music_results:
            clean_results.append({
                'id': f"{item['source']}:{item['id']}", 
                'title': item['display'],
                'uploader': item['source'].capitalize(), 
                'meta_pkg': item 
            })
        return clean_results
    return await _fallback_search(query)

async def _fallback_search(query):
    def run_search():
        opts = get_ydl_opts()
        opts['extract_flat'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Запрашиваем 100, чтобы иметь запас для фильтрации дублей
            return ydl.extract_info(f"ytsearch100:{query}", download=False)

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(executor, run_search)
        if not data or 'entries' not in data: return []
        
        clean_results = []
        seen = set()
        for entry in data['entries']:
            if not entry: continue
            title = entry.get('title', '')
            if len(title) < 2 or entry.get('duration', 0) > 1200: continue

            clean_t = format_title(title, entry.get('uploader', ''))
            
            # Уникальный ключ для фильтрации YouTube дублей
            norm_t = re.sub(r'\s+', '', clean_t.lower())
            
            if norm_t not in seen:
                seen.add(norm_t)
                clean_results.append({
                    'id': entry.get('id'),
                    'title': clean_t,
                    'uploader': 'YouTube'
                })
                # Останавливаемся ровно на 50 уникальных треках
                if len(clean_results) >= 50:
                    break
                    
        return clean_results
    except: return []

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
        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                current_filename = ydl.prepare_filename(info)
        except Exception:
            time.sleep(1.5)
            dl_opts['outtmpl'] = 'downloads/%(id)s_retry_%(epoch)s.%(ext)s'
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                current_filename = ydl.prepare_filename(info)

        if not info: raise Exception("Extraction failed")
        final_filename = current_filename.rsplit('.', 1)[0] + '.mp3'
        
        title = meta_pkg['title'] if meta_pkg else info.get('title')
        artist = meta_pkg['artist'] if meta_pkg else info.get('uploader')
        
        thumb_path = None
        if meta_pkg and meta_pkg['meta'].get('cover'):
            try:
                thumb_path = f"{info['id']}.jpg"
                with open(thumb_path, 'wb') as f: f.write(requests.get(meta_pkg['meta']['cover']).content)
            except: pass
        
        return {
            'path': final_filename,
            'title': title,
            'artist': artist,
            'thumb_path': thumb_path,
            'meta': meta_pkg['meta'] if meta_pkg else {}
        }
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, run_download)