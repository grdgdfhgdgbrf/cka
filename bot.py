
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
import stat
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

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА ДЛЯ WINDOWS ====================
def is_windows():
    return platform.system() == "Windows"

def is_linux():
    return platform.system() == "Linux"

def get_ffmpeg_path():
    """Получение пути к ffmpeg (локальная установка)"""
    # Сначала проверяем локальную установку
    local_paths = [
        os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "ffmpeg.exe"),
        os.path.join(os.getcwd(), "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(os.getcwd(), "ffmpeg.exe")
    ]
    
    for path in local_paths:
        if os.path.exists(path):
            return path
    
    # Проверяем системный PATH
    system_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if system_path:
        return system_path
    
    return None

def get_ffprobe_path():
    """Получение пути к ffprobe"""
    local_paths = [
        os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "bin", "ffprobe.exe"),
        os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "ffprobe.exe"),
        os.path.join(os.getcwd(), "ffmpeg", "bin", "ffprobe.exe"),
        os.path.join(os.getcwd(), "ffprobe.exe")
    ]
    
    for path in local_paths:
        if os.path.exists(path):
            return path
    
    system_path = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if system_path:
        return system_path
    
    return None

def download_file(url: str, dest: str):
    """Скачивание файла с прогрессом"""
    urllib.request.urlretrieve(url, dest)

def install_ffmpeg_windows():
    """Автоматическая установка FFmpeg на Windows"""
    try:
        log_message("🚀 Автоматическая установка FFmpeg для Windows...")
        
        # URL для скачивания FFmpeg
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(TOOLS_DIR, "ffmpeg.zip")
        extract_path = os.path.join(TOOLS_DIR, "ffmpeg_extract")
        
        # Скачиваем
        log_message("📥 Скачивание FFmpeg...")
        download_file(ffmpeg_url, zip_path)
        
        # Распаковываем
        log_message("📦 Распаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку bin
        bin_path = None
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        if bin_path:
            # Создаем целевую папку
            target_bin = os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "bin")
            if os.path.exists(target_bin):
                shutil.rmtree(target_bin, ignore_errors=True)
            os.makedirs(target_bin, exist_ok=True)
            
            # Копируем все файлы
            for file in os.listdir(bin_path):
                src = os.path.join(bin_path, file)
                dst = os.path.join(target_bin, file)
                shutil.copy2(src, dst)
                # Даем права на выполнение
                try:
                    os.chmod(dst, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                except:
                    pass
            
            log_message("✅ FFmpeg установлен локально")
        else:
            log_message("❌ Не найдены файлы FFmpeg", "ERROR")
            return False
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        return True
        
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def install_nodejs_windows():
    """Автоматическая установка Node.js на Windows"""
    try:
        log_message("🚀 Автоматическая установка Node.js для Windows...")
        
        node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip"
        zip_path = os.path.join(TOOLS_DIR, "nodejs.zip")
        extract_path = os.path.join(TOOLS_DIR, "nodejs_extract")
        
        # Скачиваем
        log_message("📥 Скачивание Node.js...")
        download_file(node_url, zip_path)
        
        # Распаковываем
        log_message("📦 Распаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку
        for item in os.listdir(extract_path):
            if item.startswith("node-v") and os.path.isdir(os.path.join(extract_path, item)):
                source_path = os.path.join(extract_path, item)
                target_path = os.path.join(os.getcwd(), TOOLS_DIR, "nodejs")
                
                if os.path.exists(target_path):
                    shutil.rmtree(target_path, ignore_errors=True)
                
                shutil.copytree(source_path, target_path)
                break
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        log_message("✅ Node.js установлен локально")
        return True
        
    except Exception as e:
        log_message(f"Ошибка установки Node.js: {e}", "ERROR")
        return False

def install_ffmpeg_linux():
    """Установка FFmpeg на Linux через apt"""
    try:
        log_message("🚀 Установка FFmpeg через apt...")
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        log_message("✅ FFmpeg установлен через apt")
        return True
    except Exception as e:
        log_message(f"Ошибка apt установки: {e}", "ERROR")
        return False

def auto_install_all():
    """Автоматическая установка всех зависимостей"""
    log_message("=" * 50)
    log_message("🔧 ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ")
    log_message("=" * 50)
    
    # Установка FFmpeg
    if not get_ffmpeg_path():
        log_message("⚠️ FFmpeg не найден, устанавливаю...")
        if is_windows():
            install_ffmpeg_windows()
        elif is_linux():
            install_ffmpeg_linux()
        else:
            log_message(f"⚠️ Автоустановка для {platform.system()} не поддерживается", "WARNING")
    else:
        log_message(f"✅ FFmpeg найден: {get_ffmpeg_path()}")
    
    # Установка Node.js (только для Windows, на Linux обычно уже есть)
    if is_windows():
        try:
            subprocess.run(['node', '--version'], capture_output=True, timeout=5)
            log_message("✅ Node.js уже установлен")
        except:
            log_message("⚠️ Node.js не найден, устанавливаю...")
            install_nodejs_windows()
    
    # Обновление yt-dlp
    try:
        log_message("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        log_message("✅ yt-dlp обновлён")
    except Exception as e:
        log_message(f"Ошибка обновления yt-dlp: {e}", "WARNING")
    
    log_message("=" * 50)
    log_message("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    log_message("=" * 50)

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

# ==================== РАБОТА С COOKIES ====================
def check_cookies() -> dict:
    """Проверка наличия и валидности cookies файла"""
    result = {
        'exists': False,
        'size': 0,
        'valid': False,
        'message': ''
    }
    
    if os.path.exists(COOKIES_FILE):
        result['exists'] = True
        result['size'] = os.path.getsize(COOKIES_FILE)
        
        if result['size'] > 100:
            result['valid'] = True
            result['message'] = f"✅ Cookies валидны ({result['size']} байт)"
        else:
            result['valid'] = False
            result['message'] = f"⚠️ Cookies файл слишком маленький ({result['size']} байт)"
    else:
        result['message'] = "❌ Cookies файл не найден"
    
    return result

def save_cookies_file(file_path: str) -> bool:
    """Сохранение загруженного cookies файла"""
    try:
        shutil.copy2(file_path, COOKIES_FILE)
        if os.path.exists(COOKIES_FILE):
            size = os.path.getsize(COOKIES_FILE)
            log_message(f"✅ Cookies сохранены: {size} байт")
            return True
        return False
    except Exception as e:
        log_message(f"Ошибка сохранения cookies: {e}", "ERROR")
        return False

def delete_cookies():
    """Удаление cookies файла"""
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
    try:
        ffprobe_path = get_ffprobe_path()
        if not ffprobe_path:
            log_message("⚠️ ffprobe не найден", "WARNING")
            return 60.0
        
        cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 60.0
    except Exception as e:
        log_message(f"Ошибка получения длительности: {e}", "ERROR")
        return 60.0

def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    try:
        ffmpeg_path = get_ffmpeg_path()
        if not ffmpeg_path:
            log_message("❌ FFmpeg не найден для сжатия", "ERROR")
            return None
        
        duration = get_video_duration(input_path)
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 3000000))
        
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        cmd = [
            ffmpeg_path, '-i', input_path,
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
            log_message(f"✅ Сжато: {new_size:.1f} МБ")
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
    """Скачивание видео с YouTube"""
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
            'fragment_retries': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        # Добавляем cookies если есть
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
            
            # Поиск файла
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
                    log_message("❌ Файл не найден", "ERROR")
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
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио"""
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
            f"📦 *Сжимаю видео...*\nРазмер: {file_size_mb:.1f} МБ\n⏳ Подождите",
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
                    caption=f"✅ *{title[:80]}*{cache_text} 🗜️\n📹 {quality} | {new_size:.1f} МБ",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text("❌ *Не удалось сжать*", parse_mode=ParseMode.MARKDOWN)
                return False
        else:
            await status_msg.edit_text("❌ *Ошибка сжатия*", parse_mode=ParseMode.MARKDOWN)
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
    ffmpeg_status = "✅" if get_ffmpeg_path() else "❌"
    
    await message.answer(
        f"🎬 *Видео-Бот*\n\n"
        f"📹 Отправьте ссылку на YouTube видео\n\n"
        f"*Статус:*\n"
        f"🗜️ FFmpeg: {ffmpeg_status}\n"
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
        f"🍪 *Управление cookies*\n\n"
        f"{cookies_info['message']}\n\n"
        f"*Как получить cookies:*\n"
        f"1. Установите расширение 'Get cookies.txt LOCALLY'\n"
        f"2. Войдите в YouTube\n"
        f"3. Экспортируйте cookies\n"
        f"4. Загрузите файл сюда",
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
    ffmpeg_status = "✅" if get_ffmpeg_path() else "❌"
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} видео\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🗜️ FFmpeg: {ffmpeg_status}\n"
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

# ==================== ОБРАБОТКА ФАЙЛОВ ====================
@dp.message(lambda message: message.document is not None)
async def handle_document(message: types.Message):
    """Обработка загруженных файлов"""
    document = message.document
    file_name = document.file_name
    
    if file_name == "cookies.txt" or file_name.endswith(".txt"):
        try:
            status_msg = await message.answer("⏳ *Загрузка cookies файла...*", parse_mode=ParseMode.MARKDOWN)
            
            file = await bot.get_file(document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            temp_path = os.path.join(TOOLS_DIR, "temp_cookies.txt")
            with open(temp_path, 'wb') as f:
                f.write(downloaded_file.getvalue())
            
            file_size = os.path.getsize(temp_path)
            if file_size < 100:
                await status_msg.edit_text(
                    f"❌ *Файл слишком маленький*\nРазмер: {file_size} байт\nНужно минимум 100 байт.",
                    parse_mode=ParseMode.MARKDOWN
                )
                os.remove(temp_path)
                return
            
            save_cookies_file(temp_path)
            os.remove(temp_path)
            
            if os.path.exists(COOKIES_FILE):
                final_size = os.path.getsize(COOKIES_FILE)
                await status_msg.edit_text(
                    f"✅ *Cookies успешно загружены!*\n\n"
                    f"📊 Размер: {final_size} байт\n\n"
                    f"Теперь YouTube видео должны скачиваться без проблем.",
                    parse_mode=ParseMode.MARKDOWN
                )
                log_message(f"✅ Cookies загружены пользователем {message.from_user.id}")
            else:
                await status_msg.edit_text("❌ *Ошибка сохранения cookies*", parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            log_message(f"Ошибка загрузки cookies: {e}", "ERROR")
            await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            "❌ *Неверный файл*\n\nОтправьте файл с именем `cookies.txt`",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ОБРАБОТКА ТЕКСТА И КНОПОК ====================
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
        await callback.message.edit_text(
            "📤 *Загрузите cookies файл*\n\n"
            "Просто отправьте файл `cookies.txt` в этот чат.\n\n"
            "1. Нажмите на кнопку '📎'\n"
            "2. Выберите 'Файл'\n"
            "3. Выберите cookies.txt\n"
            "4. Отправьте",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    if data == "delete_cookies":
        if delete_cookies():
            await callback.message.edit_text(
                "🗑️ *Cookies удалены*\n\nВы можете загрузить новые через /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.edit_text("❌ *Файл cookies не найден*", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "status_cookies":
        cookies_info = check_cookies()
        await callback.message.edit_text(
            f"🍪 *Статус cookies*\n\n"
            f"{cookies_info['message']}\n\n"
            f"📁 Путь: `{os.path.abspath(COOKIES_FILE) if cookies_info['exists'] else 'не существует'}`",
            parse_mode=ParseMode.MARKDOWN
        )
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
            f"⏳ *Скачиваю {quality_name}...*\nПодождите 1-2 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания*\n\nПроверьте cookies командой /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
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
        
        status_msg = await callback.message.edit_text(
            "⏳ *Скачиваю аудио...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
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
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # АВТОМАТИЧЕСКАЯ УСТАНОВКА ВСЕГО НЕОБХОДИМОГО
    auto_install_all()
    
    # Финальная проверка
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        print(f"✅ FFmpeg готов: {ffmpeg_path}")
    else:
        print("❌ FFmpeg не установлен! Проверьте ошибки выше")
    
    cookies_info = check_cookies()
    print(f"🍪 {cookies_info['message']}")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("📤 Отправьте файл cookies.txt в бота для обхода блокировки YouTube")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
