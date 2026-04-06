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
import stat
import ctypes
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
log_message(f"Загружено {len(video_cache)} записей")

# ==================== АВТОУДАЛЕНИЕ ФАЙЛОВ ====================
def cleanup_old_files():
    try:
        now = datetime.now()
        deleted_count = 0
        deleted_size = 0
        
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
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_count += 1
                            deleted_size += file_size
                            log_message(f"🗑️ Удалён старый файл: {filename}")
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

def cleanup_specific_file(file_path: str):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            log_message(f"🗑️ Удалён файл: {file_path}")
            return True
    except:
        pass
    return False

# ==================== УСТАНОВКА FFMPEG ДЛЯ WINDOWS ====================
def grant_file_permissions(file_path):
    """Выдача прав на выполнение файла"""
    try:
        os.chmod(file_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        return True
    except:
        try:
            # Альтернативный способ через attrib
            subprocess.run(['attrib', '-r', file_path], capture_output=True)
            return True
        except:
            return False

def check_ffmpeg():
    global FFMPEG_PATH, FFPROBE_PATH
    
    # Проверяем в tools папке
    local_ffmpeg = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffmpeg.exe")
    local_ffprobe = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffprobe.exe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        grant_file_permissions(local_ffmpeg)
        grant_file_permissions(local_ffprobe)
        # Проверяем, работает ли
        try:
            result = subprocess.run([local_ffmpeg, '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                FFMPEG_PATH = local_ffmpeg
                FFPROBE_PATH = local_ffprobe
                log_message(f"✅ FFmpeg работает: {FFMPEG_PATH}")
                return True
            else:
                log_message(f"⚠️ FFmpeg не отвечает", "WARNING")
        except Exception as e:
            log_message(f"⚠️ Ошибка проверки FFmpeg: {e}", "WARNING")
    
    # Проверяем в системном PATH
    system_ffmpeg = shutil.which("ffmpeg.exe")
    system_ffprobe = shutil.which("ffprobe.exe")
    if system_ffmpeg and system_ffprobe:
        FFMPEG_PATH = system_ffmpeg
        FFPROBE_PATH = system_ffprobe
        log_message(f"✅ FFmpeg найден в PATH")
        return True
    
    log_message("❌ FFmpeg не найден", "WARNING")
    return False

def install_ffmpeg_windows():
    global FFMPEG_PATH, FFPROBE_PATH
    
    try:
        log_message("🚀 Установка FFmpeg для Windows...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(TOOLS_DIR, "ffmpeg.zip")
        extract_path = os.path.join(TOOLS_DIR, "ffmpeg_extract")
        
        # Скачиваем
        log_message("📥 Скачивание FFmpeg...")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        # Распаковываем
        log_message("📦 Распаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим bin папку
        bin_path = None
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        if not bin_path:
            log_message("❌ Не найдена папка bin", "ERROR")
            return False
        
        # Создаем целевую папку
        target_bin = os.path.join(TOOLS_DIR, "ffmpeg", "bin")
        if os.path.exists(target_bin):
            shutil.rmtree(target_bin, ignore_errors=True)
        os.makedirs(target_bin, exist_ok=True)
        
        # Копируем файлы
        for file in os.listdir(bin_path):
            src = os.path.join(bin_path, file)
            dst = os.path.join(target_bin, file)
            shutil.copy2(src, dst)
            grant_file_permissions(dst)
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        # Устанавливаем пути
        FFMPEG_PATH = os.path.join(target_bin, "ffmpeg.exe")
        FFPROBE_PATH = os.path.join(target_bin, "ffprobe.exe")
        
        # Финальная проверка
        if os.path.exists(FFMPEG_PATH) and os.path.exists(FFPROBE_PATH):
            log_message(f"✅ FFmpeg установлен: {FFMPEG_PATH}")
            return True
        
        return False
        
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def ensure_ffmpeg():
    if check_ffmpeg():
        return True
    log_message("⚠️ FFmpeg не найден, начинаю установку...")
    if install_ffmpeg_windows():
        return check_ffmpeg()
    log_message("❌ Не удалось установить FFmpeg", "ERROR")
    return False

# ==================== СЖАТИЕ ВИДЕО ====================
def get_video_duration(file_path: str) -> float:
    if not FFPROBE_PATH or not os.path.exists(FFPROBE_PATH):
        return 60.0
    try:
        cmd = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 60.0
    except:
        return 60.0

def get_hardware_acceleration():
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        return 'libx264'
    try:
        result = subprocess.run([FFMPEG_PATH, '-encoders'], capture_output=True, text=True, timeout=10)
        if 'h264_nvenc' in result.stdout:
            return 'h264_nvenc'
        elif 'h264_amf' in result.stdout:
            return 'h264_amf'
        elif 'h264_qsv' in result.stdout:
            return 'h264_qsv'
        else:
            return 'libx264'
    except:
        return 'libx264'

def compress_video_fast(input_path: str, target_size_mb: int = 48) -> str:
    """Быстрое сжатие видео с обработкой ошибок"""
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        log_message("❌ FFmpeg не найден для сжатия", "ERROR")
        return None

    original_size = os.path.getsize(input_path) / (1024 * 1024)
    if original_size <= target_size_mb:
        return input_path

    duration = get_video_duration(input_path)
    if duration <= 0:
        duration = 60

    # Рассчитываем битрейт
    target_bits = target_size_mb * 8 * 1024 * 1024
    video_bitrate = int(target_bits / duration)
    video_bitrate = max(500000, min(video_bitrate, 2500000))

    base_name = os.path.basename(input_path)
    name_without_ext = os.path.splitext(base_name)[0]
    output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")

    hw = get_hardware_acceleration()
    log_message(f"⚡ Сжатие: битрейт {video_bitrate}, ускорение {hw}")

    # Используем разные подходы для обхода permission denied
    try:
        if hw == 'h264_nvenc':
            cmd = [FFMPEG_PATH, '-i', input_path,
                   '-c:v', 'h264_nvenc', '-preset', 'p1',
                   '-b:v', f'{video_bitrate}',
                   '-c:a', 'copy', '-movflags', '+faststart', '-y', output_path]
        elif hw == 'h264_amf':
            cmd = [FFMPEG_PATH, '-i', input_path,
                   '-c:v', 'h264_amf', '-usage', 'lowlatency',
                   '-b:v', f'{video_bitrate}',
                   '-c:a', 'copy', '-movflags', '+faststart', '-y', output_path]
        elif hw == 'h264_qsv':
            cmd = [FFMPEG_PATH, '-i', input_path,
                   '-c:v', 'h264_qsv', '-preset', 'veryfast',
                   '-b:v', f'{video_bitrate}',
                   '-c:a', 'copy', '-movflags', '+faststart', '-y', output_path]
        else:
            cmd = [FFMPEG_PATH, '-i', input_path,
                   '-c:v', 'libx264', '-preset', 'ultrafast',
                   '-b:v', f'{video_bitrate}',
                   '-c:a', 'copy', '-movflags', '+faststart',
                   '-threads', 'auto', '-y', output_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"Ошибка сжатия: {result.stderr[:200] if result.stderr else 'неизвестно'}")
            
            # Пробуем альтернативный метод с более низким битрейтом
            log_message("Пробую альтернативный метод сжатия...")
            alt_bitrate = int(video_bitrate * 0.7)
            alt_cmd = [FFMPEG_PATH, '-i', input_path,
                       '-c:v', 'libx264', '-preset', 'ultrafast',
                       '-b:v', f'{alt_bitrate}',
                       '-c:a', 'copy', '-movflags', '+faststart', '-y', output_path]
            alt_result = subprocess.run(alt_cmd, capture_output=True, text=True, timeout=180)
            
            if alt_result.returncode == 0 and os.path.exists(output_path):
                new_size = os.path.getsize(output_path) / (1024 * 1024)
                log_message(f"✅ Сжато альтернативным методом: {new_size:.1f} МБ")
                return output_path
            return None
            
    except subprocess.TimeoutExpired:
        log_message("❌ Таймаут сжатия")
        return None
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:40]}")
            return cached['path'], cached['title'], True

    height_map = {"144": 144, "240": 240, "360": 360, "480": 480, "720": 720, "1080": 1080, "best": 2160}
    target_h = height_map.get(quality, 720)
    
    if target_h == 2160:
        format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
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

# ==================== ОТПРАВКА С СЖАТИЕМ ====================
async def send_video_with_compress(message, file_path, title, quality, from_cache=False):
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    limit = 49
    cache_str = " 📀 (из кэша)" if from_cache else ""
    
    if file_size <= limit:
        video = FSInputFile(file_path)
        await message.answer_video(
            video, 
            caption=f"✅ *{title[:70]}*{cache_str}\n🎬 {quality}p | 📦 {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    
    status = await message.answer("⚡ *Сжимаю видео...*\n⏳ 30-60 секунд", parse_mode=ParseMode.MARKDOWN)
    loop = asyncio.get_event_loop()
    compressed = await loop.run_in_executor(None, compress_video_fast, file_path, 48)
    
    if compressed and os.path.exists(compressed):
        new_size = os.path.getsize(compressed) / (1024 * 1024)
        if new_size <= limit:
            await status.delete()
            video = FSInputFile(compressed)
            await message.answer_video(
                video,
                caption=f"✅ *{title[:70]}*{cache_str} 🗜️\n🎬 {quality}p | {new_size:.1f} МБ (было {file_size:.1f} МБ)",
                parse_mode=ParseMode.MARKDOWN
            )
            cleanup_specific_file(compressed)
            return True
        else:
            await status.edit_text(f"⚠️ *Не удалось сжать* (получилось {new_size:.1f} МБ).\nПопробуйте качество ниже.")
            cleanup_specific_file(compressed)
            return False
    else:
        await status.edit_text("❌ *Ошибка сжатия*. Попробуйте качество ниже или отправьте файл позже.")
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
        [InlineKeyboardButton(text="⚙️ Проверить FFmpeg", callback_data="admin_ffmpeg")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await message.answer("🔐 *Админ-панель*", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def admin_stats(message):
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    ffmpeg_status = "✅" if FFMPEG_PATH and os.path.exists(FFMPEG_PATH) else "❌"
    cookies_ok = "✅" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100 else "❌"
    
    downloads_count = len([f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))])
    compressed_count = len([f for f in os.listdir(COMPRESSED_DIR) if os.path.isfile(os.path.join(COMPRESSED_DIR, f))])
    
    text = (f"📊 *Статистика бота*\n\n"
            f"📁 В кэше: {len(video_cache)} видео\n"
            f"💾 Занято кэшем: {total_size:.1f} МБ\n"
            f"📂 Файлов в downloads: {downloads_count}\n"
            f"📂 Файлов в compressed: {compressed_count}\n"
            f"🎬 FFmpeg: {ffmpeg_status}\n"
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

async def admin_ffmpeg_status(message):
    if check_ffmpeg():
        hw = get_hardware_acceleration()
        await message.answer(f"🎬 *FFmpeg*: ✅ работает\n⚡ Ускорение: {hw}", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("🎬 *FFmpeg*: ❌ не работает\n🚀 Устанавливаю...", parse_mode=ParseMode.MARKDOWN)
        if ensure_ffmpeg():
            await message.answer("✅ FFmpeg успешно установлен!", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer("❌ Не удалось установить FFmpeg", parse_mode=ParseMode.MARKDOWN)

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
        "• Быстрое сжатие (30-60 секунд)\n"
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
        elif data == "admin_ffmpeg":
            await admin_ffmpeg_status(call.message)
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
        success = await send_video_with_compress(call.message, file_path, title, quality_name, from_cache)
        
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
    
    # Установка FFmpeg
    if ensure_ffmpeg():
        hw = get_hardware_acceleration()
        print(f"✅ FFmpeg готов, ускорение: {hw}")
    else:
        print("❌ FFmpeg не установлен")
    
    # Автоочистка
    deleted = cleanup_old_files()
    if deleted > 0:
        print(f"🗑️ Удалено {deleted} старых файлов")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"👥 Администраторы: {ADMIN_IDS}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
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
