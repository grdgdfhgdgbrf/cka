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
import tarfile
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
TOOLS_DIR = "tools"
COOKIES_FILE = "cookies.txt"

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR, TOOLS_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# Глобальные пути к FFmpeg
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

# ==================== УСТАНОВКА FFMPEG ДЛЯ LINUX ====================
def check_ffmpeg():
    """Проверка наличия FFmpeg в системе"""
    global FFMPEG_PATH, FFPROBE_PATH
    
    # Проверяем через which
    system_ffmpeg = shutil.which("ffmpeg")
    system_ffprobe = shutil.which("ffprobe")
    
    if system_ffmpeg and system_ffprobe:
        FFMPEG_PATH = system_ffmpeg
        FFPROBE_PATH = system_ffprobe
        log_message(f"✅ FFmpeg найден в PATH: {FFMPEG_PATH}")
        return True
    
    # Проверяем в tools папке
    local_ffmpeg = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffmpeg")
    local_ffprobe = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffprobe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        FFMPEG_PATH = local_ffmpeg
        FFPROBE_PATH = local_ffprobe
        os.chmod(FFMPEG_PATH, 0o755)
        os.chmod(FFPROBE_PATH, 0o755)
        log_message(f"✅ FFmpeg найден локально: {FFMPEG_PATH}")
        return True
    
    log_message("❌ FFmpeg не найден", "WARNING")
    return False

def install_ffmpeg_linux_apt():
    """Установка FFmpeg через apt (Debian/Ubuntu)"""
    try:
        log_message("🚀 Установка FFmpeg через apt...")
        
        # Обновляем пакеты
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        
        # Устанавливаем FFmpeg
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        
        # Проверяем установку
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_message("✅ FFmpeg установлен через apt")
            return True
        return False
    except Exception as e:
        log_message(f"Ошибка apt установки: {e}", "ERROR")
        return False

def install_ffmpeg_linux_yum():
    """Установка FFmpeg через yum (CentOS/RHEL)"""
    try:
        log_message("🚀 Установка FFmpeg через yum...")
        
        # Устанавливаем EPEL
        subprocess.run(['yum', 'install', '-y', 'epel-release'], capture_output=True, timeout=60)
        
        # Устанавливаем FFmpeg
        subprocess.run(['yum', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        
        # Проверяем установку
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_message("✅ FFmpeg установлен через yum")
            return True
        return False
    except Exception as e:
        log_message(f"Ошибка yum установки: {e}", "ERROR")
        return False

def install_ffmpeg_linux_manual():
    """Ручная установка FFmpeg (скачивание бинарников)"""
    try:
        log_message("🚀 Ручная установка FFmpeg...")
        
        # Определяем архитектуру
        arch = platform.machine()
        if arch == "x86_64":
            ffmpeg_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        elif arch == "aarch64":
            ffmpeg_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
        else:
            ffmpeg_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-i686-static.tar.xz"
        
        tar_path = os.path.join(TOOLS_DIR, "ffmpeg.tar.xz")
        extract_path = os.path.join(TOOLS_DIR, "ffmpeg_extract")
        
        # Скачиваем
        log_message(f"📥 Скачивание FFmpeg...")
        urllib.request.urlretrieve(ffmpeg_url, tar_path)
        
        # Распаковываем
        log_message("📦 Распаковка...")
        with tarfile.open(tar_path, "r:xz") as tar:
            tar.extractall(extract_path)
        
        # Находим папку с ffmpeg
        for item in os.listdir(extract_path):
            if item.startswith("ffmpeg-") and os.path.isdir(os.path.join(extract_path, item)):
                source_dir = os.path.join(extract_path, item)
                target_bin = os.path.join(TOOLS_DIR, "ffmpeg", "bin")
                
                if os.path.exists(target_bin):
                    shutil.rmtree(target_bin, ignore_errors=True)
                os.makedirs(target_bin, exist_ok=True)
                
                # Копируем файлы
                for file in ['ffmpeg', 'ffprobe']:
                    src = os.path.join(source_dir, file)
                    if os.path.exists(src):
                        dst = os.path.join(target_bin, file)
                        shutil.copy2(src, dst)
                        os.chmod(dst, 0o755)
                break
        
        # Очистка
        os.remove(tar_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        log_message("✅ FFmpeg установлен вручную")
        return True
        
    except Exception as e:
        log_message(f"Ошибка ручной установки: {e}", "ERROR")
        return False

def ensure_ffmpeg():
    """Гарантирует наличие FFmpeg"""
    global FFMPEG_PATH, FFPROBE_PATH
    
    if check_ffmpeg():
        return True
    
    log_message("⚠️ FFmpeg не найден, начинаю установку...")
    
    # Пробуем разные способы установки
    if install_ffmpeg_linux_apt():
        return check_ffmpeg()
    
    if install_ffmpeg_linux_yum():
        return check_ffmpeg()
    
    if install_ffmpeg_linux_manual():
        return check_ffmpeg()
    
    log_message("❌ Не удалось установить FFmpeg", "ERROR")
    return False

# ==================== РАБОТА С COOKIES ====================
def check_cookies() -> dict:
    result = {'exists': False, 'size': 0, 'valid': False, 'message': ''}
    
    if os.path.exists(COOKIES_FILE):
        result['exists'] = True
        result['size'] = os.path.getsize(COOKIES_FILE)
        if result['size'] > 100:
            result['valid'] = True
            result['message'] = f"✅ Cookies валидны ({result['size']} байт)"
        else:
            result['message'] = f"⚠️ Cookies файл слишком маленький ({result['size']} байт)"
    else:
        result['message'] = "❌ Cookies файл не найден"
    
    return result

def save_cookies_file(file_path: str) -> bool:
    try:
        shutil.copy2(file_path, COOKIES_FILE)
        if os.path.exists(COOKIES_FILE):
            log_message(f"✅ Cookies сохранены: {os.path.getsize(COOKIES_FILE)} байт")
            return True
        return False
    except Exception as e:
        log_message(f"Ошибка сохранения cookies: {e}", "ERROR")
        return False

def delete_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            log_message("🗑️ Cookies удалены")
            return True
        return False
    except Exception as e:
        log_message(f"Ошибка удаления cookies: {e}", "ERROR")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def get_video_duration(file_path: str) -> float:
    global FFPROBE_PATH
    
    if not FFPROBE_PATH or not os.path.exists(FFPROBE_PATH):
        return 60.0
    
    try:
        cmd = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 60.0
    except Exception as e:
        log_message(f"Ошибка получения длительности: {e}", "ERROR")
        return 60.0

def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    global FFMPEG_PATH
    
    if not FFMPEG_PATH or not os.path.exists(FFMPEG_PATH):
        log_message("❌ ffmpeg не найден для сжатия", "ERROR")
        return None
    
    try:
        duration = get_video_duration(input_path)
        
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 2000000))
        
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-b:v', f'{video_bitrate}',
            '-b:a', '128k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"Сжатие: битрейт {video_bitrate} bps, длительность {duration:.1f} сек")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            original_size = os.path.getsize(input_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            return output_path
        else:
            if result.stderr:
                log_message(f"Ошибка FFmpeg: {result.stderr[:200]}", "ERROR")
            return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:50]}")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {url[:50]}... | {quality}")
    
    try:
        quality_map = {
            "144p": 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]',
            "240p": 'bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240][ext=mp4]',
            "360p": 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]',
            "480p": 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]',
            "720p": 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]',
            "1080p": 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]',
            "best": 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
        }
        format_spec = quality_map.get(quality, 'best[ext=mp4]')
        
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
            'merge_output_format': 'mp4',
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'socket_timeout': 30,
            'retries': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
            log_message("📁 Использую cookies")
        
        with YoutubeDL(opts) as ydl:
            log_message("Получение информации...")
            info = ydl.extract_info(url, download=True)
            
            if not info:
                log_message("❌ Нет информации", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
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
            log_message(f"✅ Скачано: {title[:50]} ({file_size:.1f} МБ)")
            
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
        log_message(f"Ошибка: {e}", "ERROR")
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
            'quiet': False,
            'no_warnings': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
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
async def send_video_with_compress(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT = 49
    cache_text = " ⚡(кэш)" if from_cache else ""
    
    try:
        if file_size_mb <= LIMIT:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
        
        status_msg = await message.answer(
            f"📦 *Сжимаю видео...*\nРазмер: {file_size_mb:.1f} МБ\n⏳ Подождите 2-3 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        compressed_path = await loop.run_in_executor(None, compress_video, file_path, 48)
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:80]}*{cache_text} 🗜️\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(f"❌ *Не удалось сжать* (получилось {new_size:.1f} МБ)\nПопробуйте качество ниже", parse_mode=ParseMode.MARKDOWN)
                return False
        else:
            await status_msg.edit_text("❌ *Ошибка сжатия*\nПопробуйте качество ниже", parse_mode=ParseMode.MARKDOWN)
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
    cookies_info = check_cookies()
    ffmpeg_status = "✅" if FFMPEG_PATH and os.path.exists(FFMPEG_PATH) else "❌"
    
    await message.answer(
        f"🎬 *Видео-Бот*\n\n"
        f"📹 Отправьте ссылку на YouTube видео\n\n"
        f"*Статус:*\n"
        f"🎬 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_info['message']}\n\n"
        f"*Команды:*\n"
        f"/cookies - Управление cookies\n"
        f"/stats - Статистика\n"
        f"/clear - Очистить кэш\n"
        f"/log - Логи",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_menu_cmd(message: types.Message):
    cookies_info = check_cookies()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить cookies", callback_data="upload_cookies")],
        [InlineKeyboardButton(text="🗑️ Удалить cookies", callback_data="delete_cookies")],
        [InlineKeyboardButton(text="📊 Статус cookies", callback_data="status_cookies")]
    ])
    
    await message.answer(
        f"🍪 *Управление cookies*\n\n{cookies_info['message']}",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    cookies_info = check_cookies()
    ffmpeg_status = "✅" if FFMPEG_PATH and os.path.exists(FFMPEG_PATH) else "❌"
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} видео\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🎬 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_info['message']}",
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
            await message.answer(f"📋 *Логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("📋 Логов пока нет")

@dp.message(Command("upload_cookies"))
async def upload_cookies_command(message: types.Message):
    await message.answer(
        "📤 *Отправьте файл cookies.txt*\n\n"
        "1. Нажмите на кнопку '📎'\n"
        "2. Выберите 'Файл'\n"
        "3. Отправьте cookies.txt",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    document = message.document
    file_name = document.file_name
    
    if file_name == "cookies.txt" or file_name.endswith(".txt"):
        try:
            status_msg = await message.answer("⏳ *Загрузка...*", parse_mode=ParseMode.MARKDOWN)
            
            file = await bot.get_file(document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            temp_path = os.path.join(TOOLS_DIR, "temp_cookies.txt")
            with open(temp_path, 'wb') as f:
                f.write(downloaded_file.getvalue())
            
            file_size = os.path.getsize(temp_path)
            if file_size < 100:
                await status_msg.edit_text(f"❌ Файл слишком маленький ({file_size} байт)", parse_mode=ParseMode.MARKDOWN)
                os.remove(temp_path)
                return
            
            shutil.copy2(temp_path, COOKIES_FILE)
            os.remove(temp_path)
            
            await status_msg.edit_text(f"✅ *Cookies загружены!* ({file_size} байт)", parse_mode=ParseMode.MARKDOWN)
            log_message(f"✅ Cookies загружены пользователем {message.from_user.id}")
            
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
    
    if data == "upload_cookies":
        await callback.message.edit_text("📤 *Отправьте файл cookies.txt в этот чат*", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "delete_cookies":
        if delete_cookies():
            await callback.message.edit_text("🗑️ *Cookies удалены*", parse_mode=ParseMode.MARKDOWN)
        else:
            await callback.message.edit_text("❌ *Файл не найден*", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "status_cookies":
        cookies_info = check_cookies()
        await callback.message.edit_text(f"🍪 *Статус cookies*\n\n{cookies_info['message']}", parse_mode=ParseMode.MARKDOWN)
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
        
        quality_names = {"144p": "144p", "240p": "240p", "360p": "360p",
            "480p": "480p", "720p": "720p", "1080p": "1080p", "best": "лучшее"}
        quality_name = quality_names.get(quality, quality)
        
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачиваю {quality_name}...*\nПодождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка скачивания*\nПроверьте cookies: /cookies", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            return
        
        await status_msg.edit_text(f"📤 *Отправка...*", parse_mode=ParseMode.MARKDOWN)
        
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
                caption=f"✅ *{title[:80]}*{cache_text}\n🎵 MP3 | {file_size:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print(f"🤖 БОТ ЗАПУЩЕН")
    print(f"🖥️ Операционная система: {platform.system()} {platform.machine()}")
    print("=" * 60)
    
    # Установка FFmpeg для Linux
    if ensure_ffmpeg():
        print(f"✅ FFmpeg готов: {FFMPEG_PATH}")
        print(f"✅ ffprobe готов: {FFPROBE_PATH}")
    else:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: FFmpeg не установлен")
        print("📥 Установите FFmpeg вручную: sudo apt-get install ffmpeg")
    
    cookies_info = check_cookies()
    print(f"🍪 {cookies_info['message']}")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
