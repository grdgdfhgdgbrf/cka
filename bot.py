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
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

DOWNLOAD_DIR = "downloads"
COMPRESSED_DIR = "compressed"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"
COOKIES_FILE = "cookies.txt"

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

FFMPEG_PATH = None

# ==================== ЛОГИРОВАНИЕ ====================
def log_message(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {msg}\n")
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

# ==================== УСТАНОВКА FFMPEG ====================
def find_ffmpeg():
    """Поиск FFmpeg в системе"""
    global FFMPEG_PATH
    
    # Проверяем в PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        FFMPEG_PATH = ffmpeg
        log_message(f"✅ FFmpeg найден: {FFMPEG_PATH}")
        return True
    
    # Проверяем в стандартных местах Linux
    linux_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/bin/ffmpeg"
    ]
    for path in linux_paths:
        if os.path.exists(path):
            FFMPEG_PATH = path
            log_message(f"✅ FFmpeg найден: {FFMPEG_PATH}")
            return True
    
    log_message("❌ FFmpeg не найден", "WARNING")
    return False

def install_ffmpeg():
    """Установка FFmpeg через apt"""
    try:
        log_message("🚀 Установка FFmpeg...")
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        return find_ffmpeg()
    except Exception as e:
        log_message(f"Ошибка установки: {e}", "ERROR")
        return False

def ensure_ffmpeg():
    """Гарантия наличия FFmpeg"""
    if find_ffmpeg():
        return True
    return install_ffmpeg()

# ==================== ПРОСТОЕ СЖАТИЕ ВИДЕО ====================
def compress_video_simple(input_path: str, target_size_mb: int = 45) -> str:
    """
    Простое и надёжное сжатие видео
    Использует scale для уменьшения разрешения и фиксированный битрейт
    """
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        log_message("❌ FFmpeg не найден", "ERROR")
        return None
    
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        log_message(f"📊 Исходный размер: {original_size:.1f} МБ")
        
        # Если видео уже меньше лимита - не сжимаем
        if original_size <= target_size_mb:
            log_message(f"✅ Видео уже {original_size:.1f} МБ, сжатие не требуется")
            return input_path
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # ПРОСТАЯ КОМАНДА СЖАТИЯ
        # Уменьшаем разрешение до 720p и ставим битрейт 1.5 Mbps
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease',
            '-b:v', '1500k',
            '-b:a', '128k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"🔄 Начинаю сжатие...")
        
        # Запускаем сжатие
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Ждём завершения с таймаутом 5 минут
        try:
            stdout, stderr = process.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            process.kill()
            log_message("❌ Сжатие превысило лимит времени", "ERROR")
            return None
        
        if process.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"❌ Ошибка сжатия: {stderr[:200] if stderr else 'Неизвестная ошибка'}", "ERROR")
            return None
            
    except Exception as e:
        log_message(f"❌ Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== СЖАТИЕ С УМЕНЬШЕНИЕМ КАЧЕСТВА ====================
def compress_video_aggressive(input_path: str) -> str:
    """
    Агрессивное сжатие для очень больших файлов
    Уменьшает разрешение до 480p и сильно снижает битрейт
    """
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        return None
    
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_small.mp4")
        
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-vf', 'scale=854:480:force_original_aspect_ratio=decrease',
            '-b:v', '800k',
            '-b:a', '96k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"🔄 Агрессивное сжатие...")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        try:
            stdout, stderr = process.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            process.kill()
            return None
        
        if process.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Агрессивное сжатие: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            return output_path
        return None
        
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:50]}")
            return cached['path'], cached['title'], True
    
    log_message(f"📥 Скачивание: {url[:50]}... | {quality}")
    
    try:
        # Простые форматы
        quality_map = {
            "144p": 'worst[ext=mp4]',
            "240p": 'best[height<=240][ext=mp4]',
            "360p": 'best[height<=360][ext=mp4]',
            "480p": 'best[height<=480][ext=mp4]',
            "720p": 'best[height<=720][ext=mp4]',
            "1080p": 'best[height<=1080][ext=mp4]',
            "best": 'best[ext=mp4]'
        }
        format_spec = quality_map.get(quality, 'best[ext=mp4]')
        
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
        
        # Добавляем cookies если есть
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
            log_message("🍪 Использую cookies")
        
        with YoutubeDL(opts) as ydl:
            log_message("📡 Получение информации...")
            info = ydl.extract_info(url, download=True)
            
            if not info:
                log_message("❌ Нет информации", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Ищем файл
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
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:40]}... ({file_size:.1f} МБ)")
            
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
        log_message(f"❌ Ошибка: {e}", "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    audio_id = hashlib.md5(f"{url}_audio".encode()).hexdigest()
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
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

# ==================== ОТПРАВКА С СЖАТИЕМ ====================
async def send_video_with_compress(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT = 49
    cache_text = " ⚡(кэш)" if from_cache else ""
    
    try:
        # Если файл меньше лимита - отправляем сразу
        if file_size_mb <= LIMIT:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:70]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Отправлено без сжатия")
            return True
        
        # Пытаемся сжать
        status_msg = await message.answer(
            f"🗜️ *Сжимаю видео...*\n"
            f"📦 Размер: {file_size_mb:.1f} МБ\n"
            f"⏳ Подождите, это займёт 1-2 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        
        # Сначала пробуем обычное сжатие
        compressed_path = await loop.run_in_executor(None, compress_video_simple, file_path, 48)
        
        # Если обычное сжатие не помогло или файл всё ещё большой
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            if new_size <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:70]}*{cache_text}\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
        
        # Если обычное сжатие не помогло, пробуем агрессивное
        await status_msg.edit_text(
            f"🗜️ *Видео всё ещё большое, пробую сильное сжатие...*\n"
            f"Качество может снизиться",
            parse_mode=ParseMode.MARKDOWN
        )
        
        compressed_path2 = await loop.run_in_executor(None, compress_video_aggressive, file_path)
        
        if compressed_path2 and os.path.exists(compressed_path2):
            new_size2 = os.path.getsize(compressed_path2) / (1024 * 1024)
            if new_size2 <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path2)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:70]}*{cache_text}\n📹 {quality} | {new_size2:.1f} МБ (сильное сжатие)",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path2)
                except:
                    pass
                return True
        
        await status_msg.edit_text(
            f"❌ *Не удалось сжать видео до 50 МБ*\n"
            f"Попробуйте выбрать качество ниже (480p или 360p)",
            parse_mode=ParseMode.MARKDOWN
        )
        return False
        
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
        return False

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    ffmpeg_status = "✅" if FFMPEG_PATH else "❌"
    cookies_status = "✅" if os.path.exists(COOKIES_FILE) else "❌"
    
    await message.answer(
        f"🎬 *Видео-Бот*\n\n"
        f"📹 Отправьте ссылку на YouTube видео\n\n"
        f"*Статус:*\n"
        f"🎬 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_status}\n\n"
        f"*Команды:*\n"
        f"/cookies - Загрузить cookies\n"
        f"/stats - Статистика\n"
        f"/clear - Очистить кэш\n"
        f"/log - Логи",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_cmd(message: types.Message):
    await message.answer(
        "🍪 *Загрузка cookies*\n\n"
        "1. Установите расширение 'Get cookies.txt LOCALLY'\n"
        "2. Войдите в YouTube\n"
        "3. Экспортируйте cookies\n"
        "4. Отправьте файл сюда\n\n"
        "📤 *Отправьте файл cookies.txt*",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} видео\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear"))
async def clear_cmd(message: types.Message):
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
    await message.answer(f"🗑️ *Очищено {deleted} файлов*", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("log"))
async def log_cmd(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            log_text = "".join(last_lines)
            await message.answer(f"📋 *Логи:*\n```\n{log_text[:3000]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("📋 Логов пока нет")

@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name
    
    if file_name == "cookies.txt":
        try:
            status_msg = await message.answer("⏳ *Загрузка...*", parse_mode=ParseMode.MARKDOWN)
            
            file = await bot.get_file(document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            with open(COOKIES_FILE, 'wb') as f:
                f.write(downloaded_file.getvalue())
            
            file_size = os.path.getsize(COOKIES_FILE)
            await status_msg.edit_text(f"✅ *Cookies загружены!* ({file_size} байт)", parse_mode=ParseMode.MARKDOWN)
            log_message(f"✅ Cookies загружены")
            
        except Exception as e:
            await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("❌ *Отправьте файл cookies.txt*", parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(
        "🎥 *Выберите качество:*",
        reply_markup=get_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    if data == "cancel":
        await callback.message.edit_text("❌ *Отменено*", parse_mode=ParseMode.MARKDOWN)
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
            "480p": "480p", "720p": "720p", "1080p": "1080p", "best": "лучшее"
        }
        quality_name = quality_names.get(quality, quality)
        
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачиваю {quality_name}...*\nПодождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания*\n\n"
                "1. Загрузите cookies: /cookies\n"
                "2. Попробуйте другое качество",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        await status_msg.edit_text(f"📤 *Обработка видео...*", parse_mode=ParseMode.MARKDOWN)
        
        success = await send_video_with_compress(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.answer("❌ Ошибка")
        
    elif action == "audio":
        url = parts[1]
        
        status_msg = await callback.message.edit_text("⏳ *Скачиваю аудио...*", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка*", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " ⚡" if from_cache else ""
        
        try:
            audio_file = FSInputFile(file_path)
            await callback.message.answer_audio(
                audio=audio_file,
                caption=f"✅ *{title[:70]}*{cache_text}\n🎵 MP3 | {file_size:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    if ensure_ffmpeg():
        print(f"✅ FFmpeg: {FFMPEG_PATH}")
    else:
        print("❌ FFmpeg не установлен")
    
    cookies_exists = os.path.exists(COOKIES_FILE)
    print(f"🍪 Cookies: {'✅' if cookies_exists else '❌'}")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📁 Папка сжатия: {os.path.abspath(COMPRESSED_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
