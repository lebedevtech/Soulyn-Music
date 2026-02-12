import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
# Импортируем функцию поиска YouTube ID по названию
from bot.services import search_yt, get_audio_url, resolve_meta_to_youtube
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "Music Genie API is running"}

@app.get("/search")
async def search_music(q: str):
    if not q:
        return []
    print(f"🔎 API Search: {q}")
    results = await search_yt(q)
    return results

@app.get("/stream/{video_id}")
async def stream_track(video_id: str):
    """
    Принимает ID (YouTube, iTunes или Spotify).
    Если ID не от YouTube, находит аналог на YouTube.
    Перенаправляет на аудиопоток.
    """
    print(f"🎵 Streaming requested: {video_id}")
    
    real_vid = video_id
    
    # --- ЛОГИКА ДЛЯ ITUNES ---
    if video_id.startswith("itunes:"):
        try:
            # 1. Достаем цифры ID
            itunes_id = video_id.split(":")[1]
            
            # 2. Спрашиваем у Apple, что это за песня
            # (Используем requests внутри executor, чтобы не блочить сервер, или просто так для MVP)
            resp = requests.get(f"https://itunes.apple.com/lookup?id={itunes_id}&entity=song", timeout=5)
            data = resp.json()
            
            if data.get("resultCount", 0) > 0:
                track_info = data["results"][0]
                artist = track_info["artistName"]
                title = track_info["trackName"]
                print(f"🔄 Converting iTunes to YouTube: {artist} - {title}")
                
                # 3. Ищем этот трек на YouTube
                found_id = await resolve_meta_to_youtube(artist, title)
                if found_id:
                    real_vid = found_id
                    print(f"✅ Resolved to YouTube ID: {real_vid}")
                else:
                    print("❌ Could not find on YouTube")
        except Exception as e:
            print(f"⚠️ iTunes Resolution Error: {e}")

    # --- ЛОГИКА ДЛЯ SPOTIFY (Пока заглушка, если токена нет) ---
    elif video_id.startswith("spotify:"):
        # Тут сложнее, нужен токен. 
        # Если у тебя настроен Spotify в config.py, можно дописать похожую логику.
        print("⚠️ Spotify playback not fully implemented in API yet")

    # Получаем прямую ссылку на звук с YouTube
    direct_url = await get_audio_url(real_vid)
    
    if direct_url:
        return RedirectResponse(url=direct_url)
    else:
        return {"error": "Could not extract audio"}