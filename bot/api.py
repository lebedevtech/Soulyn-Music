from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bot.services import search_yt
import asyncio

app = FastAPI()

# Разрешаем сайту (Vercel) стучаться к нам
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # В продакшене тут будет адрес твоего сайта
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "Music Genie API is running"}

@app.get("/search")
async def search_music(q: str):
    """
    Принимает запрос ?q=Weeknd
    Возвращает список треков
    """
    if not q:
        return []
    
    print(f"🔎 API Search: {q}")
    # Используем твою готовую функцию поиска!
    results = await search_yt(q)
    return results