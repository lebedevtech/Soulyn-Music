import sqlite3
import json
import os
import time

# Настройки путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "data", "bot.db")
JSON_BACKUP = os.path.join(BASE_DIR, "data", "music_db.json.bak")

def fix_database():
    print("🚑 НАЧИНАЕМ ЛЕЧЕНИЕ БАЗЫ...")
    
    if not os.path.exists(DB_FILE):
        print("❌ Файл bot.db не найден! Сначала запусти бота хотя бы один раз.")
        return

    if not os.path.exists(JSON_BACKUP):
        print("❌ Файл music_db.json.bak не найден!")
        return

    # 1. Подключение
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # 2. Чтение бэкапа
    print("📂 Читаем JSON бэкап...")
    with open(JSON_BACKUP, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 3. Заливка данных
    print(f"🔄 Обработка {len(data)} треков...")
    updated_count = 0
    
    for vid, track in data.items():
        # Пытаемся достать данные отовсюду
        title = track.get('title')
        artist = track.get('artist')
        
        # Достаем метаданные (из корня или из meta)
        meta_block = track.get('meta', {})
        
        album = track.get('album') or meta_block.get('album')
        genre = track.get('genre') or meta_block.get('genre')
        year = track.get('year') or meta_block.get('year')
        cover = track.get('cover') or meta_block.get('cover')
        
        # Преобразуем год в строку
        if year: year = str(year)

        # Формируем полный JSON для колонки meta (на будущее)
        full_meta = {
            "album": album,
            "genre": genre,
            "year": year,
            "cover": cover
        }
        
        # SQL ЗАПРОС: Обновляем всё, что нашли
        # Мы используем INSERT OR REPLACE, чтобы обновить существующие или создать новые
        try:
            # Сначала проверяем, есть ли трек
            c.execute("SELECT popularity FROM tracks WHERE id=?", (vid,))
            row = c.fetchone()
            
            # Если трек был, сохраняем его популярность, иначе ставим 1
            current_pop = row[0] if row else 1
            if current_pop == 0: current_pop = 1 # Исправляем нули

            c.execute('''
                UPDATE tracks 
                SET title=?, artist=?, album=?, genre=?, year=?, cover=?, meta=?, popularity=?
                WHERE id=?
            ''', (title, artist, album, genre, year, cover, json.dumps(full_meta), current_pop, vid))
            
            if c.rowcount == 0:
                # Если UPDATE не сработал (трека нет), делаем INSERT
                c.execute('''
                    INSERT INTO tracks (id, file_id, title, artist, album, genre, year, cover, meta, cached_at, popularity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (vid, track.get('file_id'), title, artist, album, genre, year, cover, json.dumps(full_meta), time.time(), current_pop))
            
            updated_count += 1
            
        except Exception as e:
            print(f"⚠️ Ошибка с треком {vid}: {e}")

    conn.commit()
    conn.close()
    print(f"✅ Готово! Обновлено/Восстановлено треков: {updated_count}")
    print("🚀 Теперь можно запускать бота.")

if __name__ == "__main__":
    fix_database()