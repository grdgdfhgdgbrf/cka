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
ADMIN_ID = 5356400377  # Ваш Telegram ID для админ-панели

DOWNLOAD_DIR = "downloads"
COMPRESSED_DIR = "compressed"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"
TOOLS_DIR = "tools"
COOKIES_FILE = "cookies.txt"

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR, TOOLS_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

FFMPEG_PATH = None
FFPROBE_PATH = None

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

# ==================== УСТАНОВКА FFMPEG ====================
def check_ffmpeg():
    global FFMPEG_PATH, FFPROBE_PATH
    
    system_ffmpeg = shutil.which("ffmpeg")
    system_ffprobe = shutil.which("ffprobe")
    
    if system_ffmpeg and system_ffprobe:
        FFMPEG_PATH = system_ffmpeg
        FFPROBE_PATH = system_ffprobe
        return True
    
    local_ffmpeg = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffmpeg")
    local_ffprobe = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffprobe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        FFMPEG_PATH = local_ffmpeg
        FFPROBE_PATH = local_ffprobe
        os.chmod(FFMPEG_PATH, 0o755)
        os.chmod(FFPROBE_PATH, 0o755)
        return True
    
    return False

def install_ffmpeg():
    try:
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        return check_ffmpeg()
    except:
        return False

def ensure_ffmpeg():
    if check_ffmpeg():
        return True
    return install_ffmpeg()

# ==================== БЫСТРОЕ СЖАТИЕ ====================
def compress_video_fast(input_path: str, target_size_mb: int = 48) -> str:
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        return None
    
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        
        if original_size <= target_size_mb:
            return input_path
        
        # Получаем длительность
        duration_cmd = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
        result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        duration = float(result.stdout.strip()) if result.stdout else 60
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(500000, min(video_bitrate, 2000000))
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Быстрое сжатие
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-b:v', f'{video_bitrate}',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if os.path.exists(output_path):
            return output_path
        return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache and os.path.exists(video_cache[video_id]['path']):
        cached = video_cache[video_id]
        return cached['path'], cached['title'], True
    
    try:
        # Правильные форматы для каждого качества
        quality_formats = {
            "144p": 'worstvideo[height<=144]+worstaudio/best[height<=144]',
            "240p": 'best[height<=240]',
            "360p": 'best[height<=360]',
            "480p": 'best[height<=480]',
            "720p": 'best[height<=720]',
            "1080p": 'best[height<=1080]',
            "best": 'best'
        }
        
        format_spec = quality_formats.get(quality, 'best[height<=720]')
        
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'merge_output_format': 'mp4',
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Находим файл
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp4_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')]
                if mp4_files:
                    filename = max(mp4_files, key=os.path.getmtime)
                else:
                    return None, None, False
            
            video_cache[video_id] = {
                'path': filename,
                'title': title,
                'quality': quality,
                'url': url,
                'date': datetime.now().isoformat(),
                'size_mb': os.path.getsize(filename) / (1024 * 1024)
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    audio_id = hashlib.md5(f"{url}_audio".encode()).hexdigest()
    
    if audio_id in video_cache and os.path.exists(video_cache[audio_id]['path']):
        cached = video_cache[audio_id]
        return cached['path'], cached['title'], True
    
    try:
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
        
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
                mp3_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
                if mp3_files:
                    filename = max(mp3_files, key=os.path.getmtime)
                else:
                    return None, None, False
            
            video_cache[audio_id] = {
                'path': filename,
                'title': title,
                'type': 'audio',
                'url': url,
                'date': datetime.now().isoformat()
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА ====================
async def send_video(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT = 49
    
    cache_icon = "📦" if from_cache else "🆕"
    
    try:
        if file_size_mb <= LIMIT:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:60]}*\n\n"
                       f"{cache_icon} *Источник:* {'Кэш' if from_cache else 'Новое скачивание'}\n"
                       f"🎬 *Качество:* {quality}\n"
                       f"💾 *Размер:* {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
        
        # Сжатие
        status_msg = await message.answer(
            f"🔄 *Сжимаю видео...*\n\n"
            f"📊 *Исходный размер:* {file_size_mb:.1f} МБ\n"
            f"🎯 *Цель:* до 48 МБ\n"
            f"⏱️ *Время:* ~30-60 секунд\n\n"
            f"_Пожалуйста, подождите..._",
            parse_mode=ParseMode.MARKDOWN
        )
        
        compressed_path = await asyncio.get_event_loop().run_in_executor(
            None, compress_video_fast, file_path, 48
        )
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:60]}*\n\n"
                           f"🗜️ *Сжато:* {file_size_mb:.1f} МБ → {new_size:.1f} МБ\n"
                           f"🎬 *Качество:* {quality}\n"
                           f"⚡ *Экономия:* {file_size_mb - new_size:.1f} МБ",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(
                    f"⚠️ *Не удалось сжать видео*\n\n"
                    f"📊 *Размер после сжатия:* {new_size:.1f} МБ\n"
                    f"💡 *Совет:* Выберите качество ниже (720p или 480p)",
                    parse_mode=ParseMode.MARKDOWN
                )
                return False
        else:
            await status_msg.edit_text(
                f"❌ *Ошибка сжатия*\n\n"
                f"💡 Попробуйте выбрать качество ниже или повторите позже.",
                parse_mode=ParseMode.MARKDOWN
            )
            return False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
        return False

# ==================== КЛАВИАТУРЫ ====================
def get_quality_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 144p", callback_data=f"vid_144p_{url}"),
            InlineKeyboardButton(text="📱 240p", callback_data=f"vid_240p_{url}"),
            InlineKeyboardButton(text="📱 360p", callback_data=f"vid_360p_{url}")
        ],
        [
            InlineKeyboardButton(text="📺 480p", callback_data=f"vid_480p_{url}"),
            InlineKeyboardButton(text="📺 720p", callback_data=f"vid_720p_{url}"),
            InlineKeyboardButton(text="📺 1080p", callback_data=f"vid_1080p_{url}")
        ],
        [
            InlineKeyboardButton(text="🏆 Лучшее", callback_data=f"vid_best_{url}"),
            InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="💾 Кэш", callback_data="admin_cache")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs")
        ],
        [
            InlineKeyboardButton(text="🗑️ Очистить кэш", callback_data="admin_clear_cache"),
            InlineKeyboardButton(text="🔄 Обновить статус", callback_data="admin_status")
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")
        ]
    ])

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_name = message.from_user.first_name or "Пользователь"
    
    await message.answer(
        f"🎬 *Привет, {user_name}!*\n\n"
        f"Я бот для скачивания видео с YouTube.\n\n"
        f"📹 *Как пользоваться:*\n"
        f"1️⃣ Отправь мне ссылку на YouTube видео\n"
        f"2️⃣ Выбери нужное качество\n"
        f"3️⃣ Получи видео или аудио\n\n"
        f"⚡ *Особенности:*\n"
        f"• Автоматическое сжатие видео >50 МБ\n"
        f"• Кэширование для быстрой отправки\n"
        f"• Поддержка MP3 аудио\n\n"
        f"🔧 *Команды:*\n"
        f"/start - Главное меню\n"
        f"/help - Помощь\n"
        f"/stats - Статистика\n"
        f"/cookies - Загрузить cookies\n\n"
        f"_Для администратора есть панель управления_ 👑",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        f"📖 *Помощь*\n\n"
        f"🎯 *Как скачать видео:*\n"
        f"• Отправьте ссылку на YouTube\n"
        f"• Выберите качество из меню\n"
        f"• Дождитесь скачивания и отправки\n\n"
        f"🎵 *Как скачать аудио:*\n"
        f"• Отправьте ссылку\n"
        f"• Выберите MP3\n"
        f"• Получите аудиофайл\n\n"
        f"⚡ *Если видео >50 МБ:*\n"
        f"• Автоматически сжимается\n"
        f"• Сохраняется качество\n\n"
        f"🍪 *Если видео не скачивается:*\n"
        f"• Используйте команду /cookies\n"
        f"• Загрузите файл cookies.txt\n\n"
        f"📊 *Статистика:* /stats\n"
        f"🗑️ *Очистить кэш:* /clear",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    videos_count = 0
    audio_count = 0
    
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
            if info.get('type') == 'audio':
                audio_count += 1
            else:
                videos_count += 1
    
    size_mb = total_size / (1024 * 1024)
    size_gb = size_mb / 1024
    
    await message.answer(
        f"📊 *Статистика бота*\n\n"
        f"🎬 *Видео в кэше:* {videos_count}\n"
        f"🎵 *Аудио в кэше:* {audio_count}\n"
        f"💾 *Всего в кэше:* {videos_count + audio_count}\n\n"
        f"📦 *Занято места:*\n"
        f"• {size_mb:.1f} МБ\n"
        f"• {size_gb:.2f} ГБ\n\n"
        f"⚡ *FFmpeg:* {'✅' if check_ffmpeg() else '❌'}\n"
        f"🍪 *Cookies:* {'✅' if os.path.exists(COOKIES_FILE) else '❌'}",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear"))
async def clear_cmd(message: types.Message):
    global video_cache
    deleted = 0
    size_freed = 0
    
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            try:
                size_freed += os.path.getsize(info['path'])
                os.remove(info['path'])
                deleted += 1
            except:
                pass
    
    video_cache = {}
    save_cache(video_cache)
    
    await message.answer(
        f"🗑️ *Кэш очищен*\n\n"
        f"📁 *Удалено файлов:* {deleted}\n"
        f"💾 *Освобождено места:* {size_freed/(1024*1024):.1f} МБ",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_cmd(message: types.Message):
    await message.answer(
        f"🍪 *Загрузка cookies*\n\n"
        f"Для обхода блокировки YouTube нужно загрузить файл cookies.txt\n\n"
        f"📝 *Инструкция:*\n"
        f"1️⃣ Установите расширение 'Get cookies.txt LOCALLY'\n"
        f"2️⃣ Войдите в YouTube в браузере\n"
        f"3️⃣ Нажмите на иконку расширения\n"
        f"4️⃣ Выберите 'Export cookies'\n"
        f"5️⃣ Отправьте полученный файл сюда\n\n"
        f"📤 *Просто отправьте файл cookies.txt*",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ *Доступ запрещен*", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(
        f"👑 *Админ-панель*\n\n"
        f"Добро пожаловать в панель управления ботом.\n\n"
        f"Выберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТКА ФАЙЛОВ ====================
@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name
    
    if file_name == "cookies.txt":
        try:
            status_msg = await message.answer("⏳ *Загрузка cookies...*", parse_mode=ParseMode.MARKDOWN)
            
            file = await bot.get_file(document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            with open(COOKIES_FILE, 'wb') as f:
                f.write(downloaded_file.getvalue())
            
            file_size = os.path.getsize(COOKIES_FILE)
            await status_msg.edit_text(
                f"✅ *Cookies успешно загружены!*\n\n"
                f"📊 *Размер:* {file_size} байт\n"
                f"🍪 *Статус:* Активны\n\n"
                f"Теперь YouTube видео должны скачиваться без проблем.",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Cookies загружены пользователем {message.from_user.id}")
            
        except Exception as e:
            await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            f"❌ *Неверный файл*\n\n"
            f"Отправьте файл с именем `cookies.txt`\n"
            f"Используйте команду /cookies для инструкции.",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ОБРАБОТКА ССЫЛОК ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            f"❌ *Неверный формат*\n\n"
            f"Пожалуйста, отправьте ссылку на YouTube видео.\n"
            f"Пример: `https://youtu.be/...` или `https://www.youtube.com/...`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        f"🎥 *Выберите качество*\n\n"
        f"📹 Видео:\n"
        f"• 144p-360p - для экономии трафика\n"
        f"• 480p-720p - оптимальное качество\n"
        f"• 1080p/Live - максимальное качество\n\n"
        f"🎵 Аудио:\n"
        f"• MP3 - только звук",
        reply_markup=get_quality_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТКА КНОПОК ====================
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    # ========== АДМИН-ПАНЕЛЬ ==========
    if data == "admin_stats":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        total_size = 0
        videos_count = 0
        audio_count = 0
        
        for info in video_cache.values():
            if os.path.exists(info.get('path', '')):
                total_size += os.path.getsize(info['path'])
                if info.get('type') == 'audio':
                    audio_count += 1
                else:
                    videos_count += 1
        
        await callback.message.edit_text(
            f"📊 *Админ-статистика*\n\n"
            f"🎬 *Видео в кэше:* {videos_count}\n"
            f"🎵 *Аудио в кэше:* {audio_count}\n"
            f"📦 *Всего файлов:* {videos_count + audio_count}\n"
            f"💾 *Занято места:* {total_size/(1024*1024):.1f} МБ\n\n"
            f"⚡ *FFmpeg:* {'✅' if check_ffmpeg() else '❌'}\n"
            f"🍪 *Cookies:* {'✅' if os.path.exists(COOKIES_FILE) else '❌'}\n"
            f"📄 *Лог-файл:* {os.path.getsize(LOG_FILE)/(1024):.1f} КБ" if os.path.exists(LOG_FILE) else "",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    elif data == "admin_cache":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        cache_list = ""
        for i, (vid, info) in enumerate(list(video_cache.items())[:10]):
            size_mb = info.get('size_mb', 0)
            cache_list += f"{i+1}. {info['title'][:30]}... - {size_mb:.1f} МБ\n"
        
        await callback.message.edit_text(
            f"💾 *Содержимое кэша* (последние 10)\n\n"
            f"{cache_list}\n"
            f"📊 *Всего записей:* {len(video_cache)}",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    elif data == "admin_logs":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-20:] if len(lines) > 20 else lines
                log_text = "".join(last_lines)
                await callback.message.edit_text(
                    f"📋 *Последние логи*\n\n```\n{log_text[:2000]}\n```",
                    reply_markup=get_admin_keyboard(),
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await callback.message.edit_text("❌ Лог-файл не найден", reply_markup=get_admin_keyboard())
        await callback.answer()
        return
    
    elif data == "admin_clear_cache":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
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
        
        await callback.message.edit_text(
            f"🗑️ *Кэш очищен*\n\nУдалено файлов: {deleted}",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    elif data == "admin_status":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        await callback.message.edit_text(
            f"🔄 *Статус системы*\n\n"
            f"⚡ FFmpeg: {'✅ Работает' if check_ffmpeg() else '❌ Не установлен'}\n"
            f"🍪 Cookies: {'✅ Загружены' if os.path.exists(COOKIES_FILE) else '❌ Не загружены'}\n"
            f"💾 Кэш: {len(video_cache)} файлов\n"
            f"📁 Папки: {'✅' if os.path.exists(DOWNLOAD_DIR) else '❌'}",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    elif data == "admin_broadcast":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        await callback.message.edit_text(
            f"📢 *Рассылка*\n\n"
            f"Отправьте сообщение для рассылки всем пользователям.\n\n"
            f"Формат: `/broadcast Текст сообщения`",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    elif data == "admin_close":
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Доступ запрещен")
            return
        
        await callback.message.delete()
        await callback.answer()
        return
    
    # ========== ОСНОВНЫЕ ДЕЙСТВИЯ ==========
    if data == "cancel":
        await callback.message.edit_text("❌ *Действие отменено*", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    parts = data.split("_", 2)
    if len(parts) < 2:
        await callback.answer("Ошибка")
        return
    
    action = parts[0]
    
    if action == "vid":
        quality = parts[1]
        url = parts[2]
        
        quality_names = {
            "144p": "144p", "240p": "240p", "360p": "360p",
            "480p": "480p", "720p": "720p", "1080p": "1080p", "best": "Лучшее"
        }
        quality_name = quality_names.get(quality, quality)
        
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачиваю видео*\n\n"
            f"🎬 Качество: {quality_name}\n"
            f"📥 Статус: Получение информации...\n\n"
            f"_Пожалуйста, подождите_",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                f"❌ *Ошибка скачивания*\n\n"
                f"Возможные причины:\n"
                f"• Ссылка недействительна\n"
                f"• Видео удалено или приватно\n"
                f"• Нет cookies (команда /cookies)\n\n"
                f"💡 Попробуйте другое качество или получите cookies.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        await status_msg.edit_text(
            f"📤 *Отправка видео*\n\n"
            f"🎬 Название: {title[:40]}...\n"
            f"📦 Статус: Подготовка к отправке...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        success = await send_video(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.answer("❌ Ошибка")
        
    elif action == "audio":
        url = parts[1]
        
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачиваю аудио*\n\n"
            f"🎵 Формат: MP3\n"
            f"📥 Статус: Получение...\n\n"
            f"_Пожалуйста, подождите_",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text(
                f"❌ *Ошибка скачивания аудио*\n\n"
                f"💡 Попробуйте позже или получите cookies: /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_icon = "📦" if from_cache else "🆕"
        
        try:
            audio_file = FSInputFile(file_path)
            await callback.message.answer_audio(
                audio=audio_file,
                caption=f"✅ *{title[:60]}*\n\n"
                       f"{cache_icon} *Источник:* {'Кэш' if from_cache else 'Новое скачивание'}\n"
                       f"🎵 *Формат:* MP3\n"
                       f"💾 *Размер:* {file_size:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== РАССЫЛКА ====================
@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ *Доступ запрещен*", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("❌ *Укажите текст для рассылки*\nПример: `/broadcast Привет!`", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(f"📢 *Начинаю рассылку...*\n\nТекст: {text[:100]}", parse_mode=ParseMode.MARKDOWN)
    
    # Здесь можно добавить логику рассылки пользователям
    # Для этого нужно хранить список user_id в отдельном файле
    
    await message.answer("✅ *Рассылка завершена*", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🎬 ВИДЕО-БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    if ensure_ffmpeg():
        print("✅ FFmpeg готов")
    else:
        print("⚠️ FFmpeg не установлен")
    
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📁 Папка сжатия: {os.path.abspath(COMPRESSED_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
