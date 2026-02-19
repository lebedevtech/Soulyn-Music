import os
import re
import yt_dlp
import asyncio
import time
import httpx
import lyricsgenius
from concurrent.futures import ThreadPoolExecutor
from shazamio import Shazam
from bot.config import PROXY_URL, COOKIES_PATH, USER_AGENT, GENIUS_TOKEN, BIN_DIR
from bot.loader import logger
from bot.utils import format_title, MusicSearcher, clean_string

# --- INIT ---
shazam = Shazam()

ffmpeg_location = None
if os.path.exists(os.path.join(BIN_DIR, 'ffmpeg.exe')):
    ffmpeg_location = BIN_DIR
elif os.path.exists(os.path.join(BIN_DIR, 'ffmpeg')):
    ffmpeg_location = BIN_DIR

executor = ThreadPoolExecutor(max_workers=10)

try:
    genius = lyricsgenius.Genius(GENIUS_TOKEN, skip_non_songs=True, remove_section_headers=False, verbose=False)
except: genius = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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
        'writethumbnail': True, 
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

async def get_lyrics(artist, title):
    if not genius: return None
    clean_t = title.lower().replace(artist.lower(), "").strip()
    clean_t = clean_string(clean_t)
    loop = asyncio.get_event_loop()
    try:
        song = await loop.run_in_executor(None, lambda: genius.search_song(clean_t, artist))
        if not song:
            song = await loop.run_in_executor(None, lambda: genius.search_song(title))
            if song and artist.lower() not in song.artist.lower(): song = None
        return song.lyrics if song else None
    except: return None

def sync_search_itunes(query, limit=1):
    try:
        url = "https://itunes.apple.com/search"
        params = {"term": query, "media": "music", "entity": "song", "limit": limit}
        with httpx.Client(timeout=5) as client:
            resp = client.get(url, params=params)
            data = resp.json()
            
        if data.get("resultCount", 0) > 0:
            track = data["results"][0]
            return {
                "artist": track["artistName"],
                "title": track["trackName"],
                "meta": {
                    "album": track["collectionName"],
                    "year": track.get("releaseDate", "")[:4],
                    "genre": track.get("primaryGenreName", "Music"),
                    "cover": track.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                }
            }
    except: pass
    return None

# --- 🔥 ФУНКЦИЯ ДЛЯ API (stream endpoint) ---
async def get_audio_url(video_id):
    """Получает прямую URL аудиопотока для YouTube видео. Используется в api.py."""
    def _extract():
        opts = get_ydl_opts()
        opts['skip_download'] = True
        opts['format'] = 'bestaudio/best'
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if info:
                    # Ищем лучший аудио формат
                    formats = info.get('formats', [])
                    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') in ('none', None)]
                    if audio_formats:
                        best = max(audio_formats, key=lambda f: f.get('abr', 0) or 0)
                        return best.get('url')
                    # Fallback: берём url из info напрямую
                    return info.get('url')
        except Exception as e:
            logger.error(f"get_audio_url error: {e}")
        return None
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _extract)

# --- ПОИСК ---

async def search_yt(query: str):
    query = query.strip()
    
    # 1. Spotify Link
    if "open.spotify.com" in query or "spotify.com" in query:
        track_name = await resolve_spotify_link(query)
        if track_name: query = track_name
        else: return [] 
        
    # 2. YouTube Link
    if "youtube.com" in query or "youtu.be" in query:
        return await _resolve_youtube_link(query)

    # 3. Text Search (MusicSearcher из utils.py)
    try:
        music_results = await MusicSearcher.search_integrated(query)
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
    except Exception as e:
        logger.error(f"Search Error: {e}")
    
    # 4. Fallback (YT-DLP Search)
    return await _fallback_search(query)

async def recognize_media(file_path):
    try:
        out = await shazam.recognize(file_path)
        if 'track' in out:
            track = out['track']
            title = track.get('title')
            subtitle = track.get('subtitle')
            if title and subtitle: return f"{subtitle} - {title}"
    except: pass
    return None

async def resolve_spotify_link(url):
    def parse_page():
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            with httpx.Client(timeout=10, headers=headers) as client:
                response = client.get(url)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                page_title = soup.title.string
                return page_title.replace(" | Spotify", "").replace(" - song and lyrics by", " -").replace(" - song by", " -")
        except: pass
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_page)

async def _resolve_youtube_link(url):
    def get_info():
        opts = get_ydl_opts()
        opts['extract_flat'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, get_info)
        if not info: return []
        if 'entries' not in info:
            clean_t = format_title(info.get('title'), info.get('uploader', ''))
            return [{'id': info.get('id'), 'title': clean_t, 'uploader': 'YouTube', 'meta_pkg': None}]
        else: return [] 
    except: return []

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
            if len(title) < 2 or entry.get('duration', 0) > 1200: continue
            clean_t = format_title(title, entry.get('uploader', ''))
            norm_t = re.sub(r'\s+', '', clean_t.lower())
            if norm_t not in seen:
                seen.add(norm_t)
                clean_results.append({'id': entry.get('id'), 'title': clean_t, 'uploader': 'YouTube', 'meta_pkg': None})
                if len(clean_results) >= 20: break
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
        if data and data.get('entries'): return data['entries'][0]['id']
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
            {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
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
        except:
            time.sleep(1.5)
            try:
                dl_opts['outtmpl'] = 'downloads/%(id)s_retry.%(ext)s'
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    current_filename = ydl.prepare_filename(info)
            except: pass

        if not info: raise Exception("Extraction failed")
        
        base_name = current_filename.rsplit('.', 1)[0]
        final_filename = base_name + '.mp3'
        
        final_meta = {}
        final_title = "Unknown"
        final_artist = "Unknown"
        
        if meta_pkg:
            final_title = meta_pkg['title']
            final_artist = meta_pkg['artist']
            final_meta = meta_pkg.get('meta', {})
        else:
            raw_title = info.get('title', '')
            uploader = info.get('uploader', '')
            
            if info.get('artist') and info.get('track'):
                yt_artist = info.get('artist')
                yt_title = info.get('track')
            else:
                full_clean = format_title(raw_title, uploader)
                if " - " in full_clean: yt_artist, yt_title = full_clean.split(" - ", 1)
                else: yt_artist = uploader; yt_title = full_clean
            
            enriched = None
            try:
                search_q = f"{yt_artist} {yt_title}"
                enriched = sync_search_itunes(search_q, limit=1)
            except: pass
            
            if enriched:
                final_artist = enriched['artist']
                final_title = enriched['title']
                final_meta = enriched['meta']
            else:
                final_artist = yt_artist
                final_title = yt_title
                final_meta = {
                    'album': info.get('album'),
                    'genre': info.get('genre'),
                    'year': str(info.get('release_year') or '') if info.get('release_year') else None,
                    'cover': None 
                }

        thumb_path = None
        if final_meta.get('cover'):
            try:
                temp_thumb = f"downloads/{info['id']}_cover.jpg"
                with httpx.Client(timeout=5) as client:
                    resp = client.get(final_meta['cover'])
                    if resp.status_code == 200:
                        with open(temp_thumb, 'wb') as f: f.write(resp.content)
                        thumb_path = temp_thumb
            except: pass

        if not thumb_path:
            candidates = [base_name + ".jpg", base_name + ".webp", f"downloads/{info['id']}.jpg"]
            for c in candidates:
                if os.path.exists(c): thumb_path = c; break

        return {
            'path': final_filename,
            'title': final_title,
            'artist': final_artist,
            'thumb_path': thumb_path, 
            'meta': final_meta
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, run_download)