import re
import emoji 
import asyncio
import httpx
from contextlib import suppress
from aiogram import exceptions
from bot.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

async def delete_later(msg, delay=2.5):
    await asyncio.sleep(delay)
    with suppress(exceptions.TelegramBadRequest, exceptions.TelegramAPIError):
        await msg.delete()

JUNK_PATTERNS = [
    r'(?i)\b(hq|hd|4k|1080p|720p|mv|m/v|official|video|audio|lyrics|lyric|clip|visualizer)\b',
    r'(?i)[(\[\{]\s*(official|music|video|audio|lyric|lyrics|clip|mv|hd|hq|4k|remastered|live|cover|prod|by|feat|ft)\s*.*?[)\]\}]',
    r'(?i)\b(официальный|клип|видео|аудио|премьера|звук|текст|слова|кавер|лайв|концерт|версия|ремастер)\b',
    r'(?i)\b(полный трек|полная версия|сниппет|новинка|хит|повтори|слушать|скачать|на бите)\b',
    r'^\d+\.\s*',  # "01. Artist"
]

def clean_string(text):
    if not text: return ""
    # Убираем эмодзи
    text = emoji.replace_emoji(text, replace='')
    # Убираем мусорные слова
    for pattern in JUNK_PATTERNS:
        text = re.sub(pattern, '', text)
    # Убираем лишние пробелы и символы
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.strip(" -|.,:;[]()")
    return text

def format_title(title, artist):
    clean_t = clean_string(title)
    clean_a = clean_string(artist)
    
    # Если артист уже есть в названии (Linkin Park - Numb)
    if clean_a.lower() in clean_t.lower():
        return clean_t
    return f"{clean_a} - {clean_t}"

class MusicSearcher:
    @staticmethod
    def search_spotify(query, limit=10):
        # Заглушка, пока нет токенов. 
        # Если нужно, можно реализовать через httpx
        return []

    @staticmethod
    async def search_itunes(query, limit=10):
        # Асинхронный поиск в iTunes
        url = "https://itunes.apple.com/search"
        params = {"term": query, "media": "music", "entity": "song", "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url, params=params)
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
    async def search_integrated(cls, query):
        # Запускаем поиск параллельно (если бы был Spotify)
        # s_res = await cls.search_spotify(query) # Будущее
        i_res = await cls.search_itunes(query, limit=20)
        
        # Объединяем результаты
        combined = i_res # + s_res
        
        final_results = []
        seen = set()
        for item in combined:
            key = re.sub(r'\s+', '', f"{item['artist']}|{item['title']}".lower())
            if key not in seen:
                seen.add(key)
                final_results.append(item)
                if len(final_results) >= 50: break
        return final_results

def split_playlist_name(pl_name):
    if not pl_name: return None, ""
    parts = pl_name.split(" ", 1)
    if len(parts) == 2 and emoji.is_emoji(parts[0]):
        return parts[0], parts[1]
    return None, pl_name