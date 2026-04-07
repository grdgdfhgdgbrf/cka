import os
import asyncio
import subprocess
import sys
import json
import hashlib
import traceback
import shutil
import urllib.request
import platform
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"
ADMIN_IDS = [5356400377]  # ID администратора

DOWNLOAD_DIR = "downloads"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"
COOKIES_FILE = "cookies.txt"

FILE_LIFETIME_HOURS = 24  # Автоудаление файлов через 24 часа

for dir_name in [DOWNLOAD_DIR]:
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
        for folder in [DOWNLOAD_DIR]:
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
                            log_message(f"🗑️ Удалён старый файл: {filename}")
                        except:
                            pass
        
        # Очищаем кэш от несуществующих файлов
        to_delete = []
        for vid_id, info in video_cache.items():
            if not os.path.exists(info.get('path', '')):
                to_delete.append(vid_id)
        for vid_id in to_delete:
            del video_cache[vid_id]
        if to_delete:
            save_cache(video_cache)
            log_message(f"🗑️ Очищено {len(to_delete)} записей из кэша")
        
        return deleted_count
    except Exception as e:
        log_message(f"Ошибка автоочистки: {e}", "ERROR")
        return 0

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    """
    Скачивание видео с YouTube
    quality: 144, 240, 360, 480, 720, 1080, best
    """
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    # Проверка кэша
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:40]}")
            return cached['path'], cached['title'], True

    # Настройки качества (высота в пикселях)
    height_map = {
        "144": 144, "240": 240, "360": 360,
        "480": 480, "720": 720, "1080": 1080, "best": 2160
    }
    target_h = height_map.get(quality, 720)
    
    # Формат для скачивания
    if target_h == 2160:
        format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
    else:
        format_spec = f'bestvideo[height<={target_h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_h}][ext=mp4]'
    
    log_message(f"📥 Скачивание {quality}p (высота {target_h})...")

    opts = {
        'format': format_spec,
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s_%(height)sp.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'merge_output_format': 'mp4',
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'socket_timeout': 30,
        'retries': 10,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    }
    
    # Добавляем cookies если есть
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE
        log_message("🍪 Использую cookies")

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Поиск скачанного файла
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
                    log_message("❌ Файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:40]}... ({file_size:.1f} МБ) {quality}p")
            
            # Сохраняем в кэш
            video_cache[video_id] = {
                'path': filename,
                'title': title,
                'quality': quality,
                'url': url,
                'date': datetime.now().isoformat(),
                'size_mb': file_size
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"❌ Ошибка скачивания: {e}", "ERROR")
        return None, None, False

# ==================== СКАЧИВАНИЕ АУДИО (MP3) ====================
def download_audio_sync(url: str):
    """Скачивание только аудио в формате MP3"""
    audio_id = hashlib.md5(f"{url}_mp3".encode()).hexdigest()
    
    # Проверка кэша
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Аудио из кэша: {cached['title'][:40]}")
            return cached['path'], cached['title'], True
    
    log_message("🎵 Скачивание аудио в MP3...")
    
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    }
    
    # Добавляем cookies если есть
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE
        log_message("🍪 Использую cookies")
    
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Поиск MP3 файла
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp3') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp3s = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
                if mp3s:
                    filename = max(mp3s, key=os.path.getmtime)
                    log_message(f"📁 Найден файл: {os.path.basename(filename)}")
                else:
                    log_message("❌ MP3 файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Аудио скачано: {title[:40]}... ({file_size:.1f} МБ)")
            
            # Сохраняем в кэш
            video_cache[audio_id] = {
                'path': filename,
                'title': title,
                'type': 'audio',
                'url': url,
                'date': datetime.now().isoformat(),
                'size_mb': file_size
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"❌ Ошибка скачивания аудио: {e}", "ERROR")
        return None, None, False

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
    
    # Считаем количество видео и аудио
    videos_count = sum(1 for info in video_cache.values() if info.get('type') != 'audio')
    audios_count = sum(1 for info in video_cache.values() if info.get('type') == 'audio')
    
    downloads_count = len([f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))])
    
    text = (f"📊 *Статистика бота*\n\n"
            f"🎬 Видео в кэше: {videos_count}\n"
            f"🎵 Аудио в кэше: {audios_count}\n"
            f"💾 Занято места: {total_size:.1f} МБ\n"
            f"📂 Файлов на диске: {downloads_count}\n"
            f"🍪 Cookies: {cookies_ok}\n"
            f"🖥️ ОС: {platform.system()}")
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

async def admin_clear(message):
    """Очистка только кэша (без удаления файлов)"""
    global video_cache
    video_cache = {}
    save_cache(video_cache)
    await message.answer("🗑️ *Кэш очищен*", parse_mode=ParseMode.MARKDOWN)

async def admin_clean_all(message):
    """Полная очистка всех файлов и кэша"""
    deleted = 0
    for folder in [DOWNLOAD_DIR]:
        if os.path.exists(folder):
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
        await message.answer("📜 Лог-файл не найден")

async def admin_cookies_status(message):
    if os.path.exists(COOKIES_FILE):
        size = os.path.getsize(COOKIES_FILE)
        await message.answer(f"🍪 *Cookies*: ✅ найден\n📦 Размер: {size} байт", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            "🍪 *Cookies*: ❌ не найден\n\n"
            "📤 Отправьте файл cookies.txt боту\n\n"
            "Как получить cookies:\n"
            "1. Установите расширение 'Get cookies.txt LOCALLY'\n"
            "2. Войдите в YouTube\n"
            "3. Экспортируйте cookies\n"
            "4. Отправьте файл сюда",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_quality_keyboard(url: str):
    """Клавиатура выбора качества"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p (маленькое)", callback_data=f"vid_144_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480_{url}"),
         InlineKeyboardButton(text="🎬 720p (рекомендуется)", callback_data=f"vid_720_{url}"),
         InlineKeyboardButton(text="🎬 1080p (Full HD)", callback_data=f"vid_1080_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее качество", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3 (только аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *YouTube Видео-Бот*\n\n"
        "📹 Отправьте ссылку на YouTube видео, и я скачаю его в нужном качестве.\n\n"
        "*🎮 Доступные качества:*\n"
        "• 144p — самое маленькое, быстро\n"
        "• 240p, 360p, 480p — среднее качество\n"
        "• 720p — рекомендуется (хорошее качество)\n"
        "• 1080p — Full HD (большой размер)\n"
        "• Лучшее — максимальное доступное\n"
        "• MP3 — только аудио\n\n"
        "*⚡ Особенности:*\n"
        "• Чем выше качество — тем лучше видео, но больше размер\n"
        "• Кэширование — повторные видео мгновенно\n"
        "• Автоудаление файлов через 24 часа\n\n"
        "📥 /cookies — инструкция по cookies\n"
        "🔧 /admin — админ-панель",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_help(message: types.Message):
    await message.answer(
        "🍪 *Инструкция по получению cookies*\n\n"
        "1️⃣ Установите расширение для браузера:\n"
        "   • Chrome: 'Get cookies.txt LOCALLY'\n"
        "   • Firefox: 'cookies.txt'\n\n"
        "2️⃣ Войдите в свой аккаунт YouTube\n\n"
        "3️⃣ Нажмите на иконку расширения и выберите 'Export cookies'\n\n"
        "4️⃣ Сохраните файл как `cookies.txt`\n\n"
        "5️⃣ Отправьте этот файл боту (просто перетащите в чат)\n\n"
        "✅ После загрузки бот сможет скачивать любые видео без блокировок!",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    await admin_panel(message)

@dp.message(Command("stats"))
async def stats_short_cmd(message: types.Message):
    """Краткая статистика для пользователей"""
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    await message.answer(
        f"📊 *Краткая статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} файлов\n"
        f"💾 Занято: {total_size:.1f} МБ",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear"))
async def clear_short_cmd(message: types.Message):
    """Быстрая очистка для пользователей"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 *Доступ запрещён*. Используйте /admin", parse_mode=ParseMode.MARKDOWN)
        return
    await admin_clean_all(message)

@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    """Обработка загруженных файлов cookies"""
    if message.document.file_name == "cookies.txt":
        try:
            status = await message.answer("⏳ *Загрузка cookies...*", parse_mode=ParseMode.MARKDOWN)
            file = await bot.get_file(message.document.file_id)
            data = await bot.download_file(file.file_path)
            with open(COOKIES_FILE, 'wb') as f:
                f.write(data.getvalue())
            size = os.path.getsize(COOKIES_FILE)
            await status.edit_text(f"✅ *Cookies загружены!* ({size} байт)\n\nТеперь бот может скачивать любые видео!", parse_mode=ParseMode.MARKDOWN)
            log_message(f"✅ Cookies загружены пользователем {message.from_user.id}")
        except Exception as e:
            await message.answer(f"❌ *Ошибка загрузки:* {e}", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            "❌ *Неверный файл*\n\n"
            "Отправьте файл с именем `cookies.txt`\n"
            "Инструкция: /cookies",
            parse_mode=ParseMode.MARKDOWN
        )

@dp.message()
async def handle_url(message: types.Message):
    """Обработка ссылок"""
    url = message.text.strip()
    log_message(f"🔗 Ссылка от {message.from_user.id}: {url[:80]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            "❌ *Отправьте ссылку на видео*\n\n"
            "Ссылка должна начинаться с http:// или https://\n"
            "Пример: https://youtu.be/... или https://www.youtube.com/...",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        "🎥 *Выберите качество видео:*\n\n"
        "💡 *Совет:* Чем выше качество, тем лучше видео, но больше размер.\n"
        "• 720p — оптимальный выбор\n"
        "• 1080p — отличное качество, но большой размер\n"
        "• MP3 — только звук",
        reply_markup=get_quality_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query()
async def callback_handler(call: CallbackQuery):
    """Обработка нажатий кнопок"""
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

    # Обработка выбора качества
    parts = data.split("_", 2)
    if len(parts) < 2:
        await call.answer("Ошибка формата")
        return
    
    action = parts[0]
    
    # Видео
    if action == "vid":
        quality = parts[1]  # 144, 240, 360, 480, 720, 1080, best
        url = parts[2]
        
        quality_names = {
            "144": "144p", "240": "240p", "360": "360p",
            "480": "480p", "720": "720p", "1080": "1080p", "best": "лучшее"
        }
        quality_name = quality_names.get(quality, quality + "p")
        
        status_msg = await call.message.edit_text(
            f"⏳ *Скачиваю {quality_name}...*\n"
            f"📹 Подождите, это может занять 1-3 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания*\n\n"
                "Возможные причины:\n"
                "• Не загружены cookies (/cookies)\n"
                "• Видео удалено или приватно\n"
                "• Выбранное качество недоступно\n\n"
                "Попробуйте другое качество или получите cookies",
                parse_mode=ParseMode.MARKDOWN
            )
            await call.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " 📀 (из кэша)" if from_cache else ""
        
        await status_msg.edit_text(f"📤 *Отправляю видео...*", parse_mode=ParseMode.MARKDOWN)
        
        video = FSInputFile(file_path)
        await call.message.answer_video(
            video,
            caption=f"✅ *{title[:70]}*{cache_text}\n"
                    f"🎬 Качество: {quality_name} | 📦 {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await status_msg.delete()
        await call.answer("✅ Видео отправлено!")
    
    # Аудио
    elif action == "audio":
        url = parts[1]
        
        status_msg = await call.message.edit_text(
            "⏳ *Скачиваю аудио в MP3...*\n"
            "🎵 Подождите, это может занять 1-2 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания аудио*\n\n"
                "Возможные причины:\n"
                "• Не загружены cookies (/cookies)\n"
                "• Видео не найдено",
                parse_mode=ParseMode.MARKDOWN
            )
            await call.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " 📀 (из кэша)" if from_cache else ""
        
        await status_msg.edit_text(f"📤 *Отправляю аудио...*", parse_mode=ParseMode.MARKDOWN)
        
        audio = FSInputFile(file_path)
        await call.message.answer_audio(
            audio,
            caption=f"✅ *{title[:70]}*{cache_text}\n"
                    f"🎵 MP3 | 📦 {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await status_msg.delete()
        await call.answer("✅ Аудио отправлено!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🎬 YouTube ВИДЕО-БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Проверка cookies
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        print("✅ Cookies загружены")
    else:
        print("⚠️ Cookies не найдены")
        print("📤 Отправьте файл cookies.txt боту (команда /cookies)")
    
    # Автоочистка при запуске
    deleted = cleanup_old_files()
    if deleted > 0:
        print(f"🗑️ Удалено {deleted} старых файлов")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"👥 Администраторы: {ADMIN_IDS}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("📌 Отправьте ссылку на YouTube видео")
    print("=" * 60)
    
    # Периодическая очистка каждый час
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(3600)
            cleanup_old_files()
    
    asyncio.create_task(periodic_cleanup())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
