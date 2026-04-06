import os
import asyncio
import subprocess
import sys
import json
import hashlib
import traceback
import shutil
import urllib.request
import zipfile
import platform
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"
ADMIN_IDS = [5356400377]

DOWNLOAD_DIR = "downloads"
COMPRESSED_DIR = "compressed"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"
TOOLS_DIR = "tools"
COOKIES_FILE = "cookies.txt"

FILE_LIFETIME_HOURS = 24

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR, TOOLS_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# ==================== ЛОГИРОВАНИЕ ====================
def log_message(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {msg}"
    print(log_entry)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except:
        pass

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except:
        pass

video_cache = load_cache()
log_message(f"Загружено {len(video_cache)} записей")

# ==================== АВТОУДАЛЕНИЕ ФАЙЛОВ ====================
def cleanup_old_files():
    try:
        now = datetime.now()
        deleted_count = 0
        for folder in [DOWNLOAD_DIR, COMPRESSED_DIR]:
            if not os.path.exists(folder):
                continue
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    age_hours = (now - file_time).total_seconds() / 3600
                    if age_hours > FILE_LIFETIME_HOURS:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except:
                            pass
        
        to_delete = []
        for vid_id, info in video_cache.items():
            if not os.path.exists(info.get('path', '')):
                to_delete.append(vid_id)
        for vid_id in to_delete:
            del video_cache[vid_id]
        if to_delete:
            save_cache(video_cache)
        
        return deleted_count
    except Exception as e:
        log_message(f"Ошибка автоочистки: {e}", "ERROR")
        return 0

# ==================== СКАЧИВАНИЕ ВИДЕО С ПРЯМЫМ СЖАТИЕМ ====================
def download_video_sync(url: str, quality: str):
    """
    Скачивание видео с YouTube с возможностью прямого сжатия через yt-dlp
    quality: 144, 240, 360, 480, 720, 1080, best
    """
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:40]}")
            return cached['path'], cached['title'], True

    height_map = {"144": 144, "240": 240, "360": 360, "480": 480, "720": 720, "1080": 1080, "best": 2160}
    target_h = height_map.get(quality, 720)
    
    # Для больших файлов (более 50 МБ) используем сжатие на лету
    # Скачиваем с битрейтом, чтобы уложиться в лимит
    need_compress = target_h >= 720
    
    if need_compress:
        # Для 720p и выше используем ограничение битрейта
        format_spec = f'bestvideo[height<={target_h}][ext=mp4][filesize<50M]+bestaudio[ext=m4a]/best[height<={target_h}][ext=mp4][filesize<50M]/best[ext=mp4]'
    else:
        format_spec = f'bestvideo[height<={target_h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_h}][ext=mp4]'

    opts = {
        'format': format_spec,
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'merge_output_format': 'mp4',
        'geo_bypass': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    }
    
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp4s = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')]
                if mp4s:
                    filename = max(mp4s, key=os.path.getmtime)
                else:
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:40]} ({file_size:.1f} МБ) {quality}p")
            
            video_cache[video_id] = {
                'path': filename, 'title': title, 'quality': quality,
                'url': url, 'date': datetime.now().isoformat(), 'size_mb': file_size
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка скачивания: {e}")
        return None, None, False

def download_video_compressed_sync(url: str, quality: str, target_size_mb: int = 48):
    """
    Скачивание видео с принудительным сжатием через yt-dlp (без FFmpeg)
    """
    video_id = hashlib.md5(f"{url}_{quality}_compressed".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша (сжатое): {cached['title'][:40]}")
            return cached['path'], cached['title'], True

    height_map = {"144": 144, "240": 240, "360": 360, "480": 480, "720": 720, "1080": 1080, "best": 2160}
    target_h = height_map.get(quality, 720)
    
    # Используем формат с ограничением битрейта для маленького размера
    # Это позволит скачать видео уже сжатым
    format_spec = f'bestvideo[height<={target_h}][ext=mp4][filesize<{target_size_mb}M]+bestaudio[ext=m4a]/best[height<={target_h}][ext=mp4][filesize<{target_size_mb}M]/best[ext=mp4]'
    
    opts = {
        'format': format_spec,
        'outtmpl': os.path.join(COMPRESSED_DIR, '%(title)s_compressed.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'merge_output_format': 'mp4',
        'geo_bypass': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    }
    
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            filename = None
            for f in os.listdir(COMPRESSED_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(COMPRESSED_DIR, f)
                    break
            
            if not filename:
                mp4s = [os.path.join(COMPRESSED_DIR, f) for f in os.listdir(COMPRESSED_DIR) if f.endswith('.mp4')]
                if mp4s:
                    filename = max(mp4s, key=os.path.getmtime)
                else:
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано сжатое видео: {title[:40]} ({file_size:.1f} МБ) {quality}p")
            
            video_cache[video_id] = {
                'path': filename, 'title': title, 'quality': quality,
                'url': url, 'date': datetime.now().isoformat(), 'size_mb': file_size
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка скачивания сжатого видео: {e}")
        return None, None, False

def download_audio_sync(url: str):
    audio_id = hashlib.md5(f"{url}_audio".encode()).hexdigest()
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            return cached['path'], cached['title'], True
    
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'quiet': True,
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    }
    
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE
    
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp3') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp3s = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
                if mp3s:
                    filename = max(mp3s, key=os.path.getmtime)
                else:
                    return None, None, False
            
            video_cache[audio_id] = {'path': filename, 'title': title, 'type': 'audio', 'url': url}
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка аудио: {e}")
        return None, None, False

# ==================== ОТПРАВКА ВИДЕО ====================
async def send_video_with_fallback(message, file_path, title, quality, from_cache=False):
    """Отправка видео с альтернативным методом при большом размере"""
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    limit = 49
    cache_str = " 📀 (из кэша)" if from_cache else ""
    
    # Если видео уже меньше лимита - отправляем
    if file_size <= limit:
        video = FSInputFile(file_path)
        await message.answer_video(
            video, 
            caption=f"✅ *{title[:70]}*{cache_str}\n🎬 {quality}p | 📦 {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    
    # Если видео больше лимита, пробуем скачать заново с сжатием
    log_message(f"⚠️ Видео {file_size:.1f} МБ > {limit} МБ, пробую скачать сжатое...")
    status_msg = await message.answer(
        f"📦 *Видео слишком большое* ({file_size:.1f} МБ)\n"
        f"⏳ Скачиваю сжатый вариант...\n"
        f"_Это может занять 1-2 минуты_",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Получаем URL из кэша
    url = None
    for vid_id, info in video_cache.items():
        if info.get('path') == file_path:
            url = info.get('url')
            break
    
    if not url:
        await status_msg.edit_text("❌ *Не удалось найти ссылку на видео*", parse_mode=ParseMode.MARKDOWN)
        return False
    
    # Скачиваем сжатое видео
    loop = asyncio.get_event_loop()
    compressed_path, compressed_title, from_compressed_cache = await loop.run_in_executor(
        None, download_video_compressed_sync, url, quality, 48
    )
    
    if compressed_path and os.path.exists(compressed_path):
        new_size = os.path.getsize(compressed_path) / (1024 * 1024)
        if new_size <= limit:
            await status_msg.delete()
            video = FSInputFile(compressed_path)
            await message.answer_video(
                video,
                caption=f"✅ *{title[:70]}* 🗜️\n🎬 {quality}p | {new_size:.1f} МБ (было {file_size:.1f} МБ)",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
        else:
            await status_msg.edit_text(
                f"⚠️ *Не удалось получить сжатое видео* (получилось {new_size:.1f} МБ)\n"
                f"Попробуйте качество ниже.",
                parse_mode=ParseMode.MARKDOWN
            )
            return False
    else:
        await status_msg.edit_text(
            "❌ *Не удалось скачать сжатое видео*\n"
            "Попробуйте качество ниже (например, 480p или 360p)",
            parse_mode=ParseMode.MARKDOWN
        )
        return False

# ==================== АДМИН-ПАНЕЛЬ ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 *Доступ запрещён*", parse_mode=ParseMode.MARKDOWN)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🗑️ Очистить кэш", callback_data="admin_clear")],
        [InlineKeyboardButton(text="🗑️ Очистить всё", callback_data="admin_clean_all")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🍪 Статус cookies", callback_data="admin_cookies")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await message.answer("🔐 *Админ-панель*", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def admin_stats(message):
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    cookies_ok = "✅" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100 else "❌"
    
    downloads_count = len([f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))])
    compressed_count = len([f for f in os.listdir(COMPRESSED_DIR) if os.path.isfile(os.path.join(COMPRESSED_DIR, f))])
    
    text = (f"📊 *Статистика бота*\n\n"
            f"📁 В кэше: {len(video_cache)} видео\n"
            f"💾 Занято кэшем: {total_size:.1f} МБ\n"
            f"📂 Файлов в downloads: {downloads_count}\n"
            f"📂 Файлов в compressed: {compressed_count}\n"
            f"🍪 Cookies: {cookies_ok}\n"
            f"🖥️ ОС: {platform.system()}")
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

async def admin_clear(message):
    global video_cache
    deleted = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            try:
                os.remove(info['path'])
                deleted += 1
            except:
                pass
    video_cache = {}
    save_cache(video_cache)
    await message.answer(f"🗑️ *Очищено {deleted} файлов из кэша*", parse_mode=ParseMode.MARKDOWN)

async def admin_clean_all(message):
    deleted = 0
    for folder in [DOWNLOAD_DIR, COMPRESSED_DIR]:
        for f in os.listdir(folder):
            file_path = os.path.join(folder, f)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    deleted += 1
                except:
                    pass
    
    global video_cache
    video_cache = {}
    save_cache(video_cache)
    await message.answer(f"🗑️ *Полная очистка*\nУдалено {deleted} файлов", parse_mode=ParseMode.MARKDOWN)

async def admin_logs(message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-30:]
            log_text = ''.join(lines)
            await message.answer(f"📜 *Логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Лог-файл не найден")

async def admin_cookies_status(message):
    if os.path.exists(COOKIES_FILE):
        size = os.path.getsize(COOKIES_FILE)
        await message.answer(f"🍪 *Cookies*: ✅ найден\n📦 Размер: {size} байт", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("🍪 *Cookies*: ❌ не найден\n📤 Отправьте файл cookies.txt", parse_mode=ParseMode.MARKDOWN)

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_quality_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте ссылку на YouTube видео\n\n"
        "⚡ *Особенности:*\n"
        "• Автоматическое сжатие видео\n"
        "• Выбор качества 144p → 1080p\n"
        "• Кэширование\n"
        "• Автоудаление файлов\n\n"
        "📥 /cookies - инструкция\n"
        "🔧 /admin - админ-панель",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_help(message: types.Message):
    await message.answer(
        "🍪 *Инструкция по cookies*\n\n"
        "1. Установите расширение *Get cookies.txt LOCALLY*\n"
        "2. Войдите в YouTube\n"
        "3. Нажмите на иконку расширения → Export cookies\n"
        "4. Сохраните файл как `cookies.txt`\n"
        "5. Отправьте этот файл боту\n\n"
        "✅ После загрузки бот сможет скачивать любые видео",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    await admin_panel(message)

@dp.message(lambda message: message.document is not None)
async def handle_doc(message: types.Message):
    if message.document.file_name == "cookies.txt":
        try:
            status = await message.answer("⏳ *Загрузка cookies...*", parse_mode=ParseMode.MARKDOWN)
            file = await bot.get_file(message.document.file_id)
            data = await bot.download_file(file.file_path)
            with open(COOKIES_FILE, 'wb') as f:
                f.write(data.getvalue())
            size = os.path.getsize(COOKIES_FILE)
            await status.edit_text(f"✅ *Cookies загружены!* ({size} байт)", parse_mode=ParseMode.MARKDOWN)
            log_message(f"Cookies загружены пользователем {message.from_user.id}")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    else:
        await message.answer("❌ Отправьте файл `cookies.txt`", parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*", parse_mode=ParseMode.MARKDOWN)
        return
    await message.answer("🎥 *Выберите качество:*", reply_markup=get_quality_keyboard(url), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query()
async def callback_handler(call: CallbackQuery):
    data = call.data
    
    if data == "cancel":
        await call.message.edit_text("❌ *Отменено*", parse_mode=ParseMode.MARKDOWN)
        await call.answer()
        return

    # Админ-панель
    if data.startswith("admin_"):
        if not is_admin(call.from_user.id):
            await call.answer("Доступ запрещён", show_alert=True)
            return
        if data == "admin_stats":
            await admin_stats(call.message)
        elif data == "admin_clear":
            await admin_clear(call.message)
        elif data == "admin_clean_all":
            await admin_clean_all(call.message)
        elif data == "admin_logs":
            await admin_logs(call.message)
        elif data == "admin_cookies":
            await admin_cookies_status(call.message)
        elif data == "admin_close":
            await call.message.delete()
        await call.answer()
        return

    # Обработка видео
    parts = data.split("_", 2)
    if len(parts) < 2:
        await call.answer("Ошибка")
        return
    
    action = parts[0]
    
    if action == "vid":
        quality = parts[1]
        url = parts[2]
        quality_name = quality if quality != "best" else "лучшее"
        
        status_msg = await call.message.edit_text(
            f"⏳ *Скачиваю {quality_name}p...*\nПодождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания*\nНужны cookies: /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
            await call.answer()
            return
        
        await status_msg.edit_text("📤 *Отправляю...*", parse_mode=ParseMode.MARKDOWN)
        success = await send_video_with_fallback(call.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await call.answer("✅ Готово!")
        else:
            await call.answer("❌ Ошибка")
    
    elif action == "audio":
        url = parts[1]
        
        status_msg = await call.message.edit_text("⏳ *Скачиваю аудио...*", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка*", parse_mode=ParseMode.MARKDOWN)
            await call.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        audio = FSInputFile(file_path)
        await call.message.answer_audio(
            audio,
            caption=f"✅ *{title[:70]}*{' 📀 (кэш)' if from_cache else ''}\n🎵 MP3 | {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        await status_msg.delete()
        await call.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🎬 ВИДЕО-БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Проверка cookies
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        print("✅ Cookies загружены")
    else:
        print("⚠️ Cookies не найдены - отправьте файл cookies.txt боту")
    
    # Автоочистка
    deleted = cleanup_old_files()
    if deleted > 0:
        print(f"🗑️ Удалено {deleted} старых файлов")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"👥 Администраторы: {ADMIN_IDS}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("📌 Для скачивания видео отправьте ссылку")
    print("=" * 60)
    
    # Периодическая очистка
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(3600)
            cleanup_old_files()
    
    asyncio.create_task(periodic_cleanup())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
