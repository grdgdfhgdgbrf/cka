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

# Пути для Windows
if platform.system() == "Windows":
    FFMPEG_DIR = os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg")
    FFMPEG_BIN = os.path.join(FFMPEG_DIR, "bin")
    os.environ['PATH'] = FFMPEG_BIN + os.pathsep + os.environ.get('PATH', '')

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

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА FFMPEG ДЛЯ WINDOWS ====================
def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg"""
    # Проверяем в папке tools
    if platform.system() == "Windows":
        ffmpeg_exe = os.path.join(FFMPEG_BIN, "ffmpeg.exe")
        if os.path.exists(ffmpeg_exe):
            log_message(f"✅ FFmpeg найден: {ffmpeg_exe}")
            return True
    
    # Проверяем в PATH
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            log_message("✅ FFmpeg найден в PATH")
            return True
    except:
        pass
    
    log_message("❌ FFmpeg не найден")
    return False

def download_ffmpeg():
    """Скачивание FFmpeg для Windows"""
    try:
        log_message("📥 Скачивание FFmpeg...")
        
        # URL для скачивания FFmpeg (стабильная версия)
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(TOOLS_DIR, "ffmpeg.zip")
        
        # Скачиваем
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        log_message("✅ FFmpeg скачан")
        return zip_path
    except Exception as e:
        log_message(f"Ошибка скачивания FFmpeg: {e}", "ERROR")
        return None

def extract_ffmpeg(zip_path):
    """Распаковка FFmpeg"""
    try:
        log_message("📦 Распаковка FFmpeg...")
        extract_path = os.path.join(TOOLS_DIR, "ffmpeg_temp")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку bin
        for item in os.listdir(extract_path):
            if item.startswith("ffmpeg-") and os.path.isdir(os.path.join(extract_path, item)):
                source_bin = os.path.join(extract_path, item, "bin")
                if os.path.exists(source_bin):
                    # Создаем целевую папку
                    os.makedirs(FFMPEG_BIN, exist_ok=True)
                    
                    # Копируем все файлы
                    for file in os.listdir(source_bin):
                        src = os.path.join(source_bin, file)
                        dst = os.path.join(FFMPEG_BIN, file)
                        shutil.copy2(src, dst)
                        # Даем права на выполнение
                        try:
                            os.chmod(dst, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                        except:
                            pass
                    
                    log_message("✅ FFmpeg распакован")
                    break
        
        # Удаляем временные файлы
        shutil.rmtree(extract_path, ignore_errors=True)
        os.remove(zip_path)
        
        return True
    except Exception as e:
        log_message(f"Ошибка распаковки FFmpeg: {e}", "ERROR")
        return False

def install_ffmpeg_windows():
    """Полная установка FFmpeg на Windows"""
    log_message("🚀 Автоматическая установка FFmpeg для Windows...")
    
    # Скачиваем
    zip_path = download_ffmpeg()
    if not zip_path:
        return False
    
    # Распаковываем
    if extract_ffmpeg(zip_path):
        # Проверяем установку
        if check_ffmpeg():
            log_message("✅ FFmpeg успешно установлен!")
            return True
    
    log_message("❌ Не удалось установить FFmpeg", "ERROR")
    return False

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
    """Получение длительности видео через ffprobe"""
    try:
        # Определяем путь к ffprobe
        if platform.system() == "Windows":
            ffprobe_path = os.path.join(FFMPEG_BIN, "ffprobe.exe")
            if not os.path.exists(ffprobe_path):
                ffprobe_path = "ffprobe"
        else:
            ffprobe_path = "ffprobe"
        
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
    """Сжатие видео с помощью FFmpeg"""
    try:
        # Определяем путь к ffmpeg
        if platform.system() == "Windows":
            ffmpeg_path = os.path.join(FFMPEG_BIN, "ffmpeg.exe")
            if not os.path.exists(ffmpeg_path):
                ffmpeg_path = "ffmpeg"
        else:
            ffmpeg_path = "ffmpeg"
        
        # Проверяем наличие ffmpeg
        result = subprocess.run([ffmpeg_path, '-version'], capture_output=True, timeout=5)
        if result.returncode != 0:
            log_message("❌ FFmpeg не работает", "ERROR")
            return None
        
        # Получаем длительность
        duration = get_video_duration(input_path)
        if duration <= 0:
            duration = 60
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 3000000))
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Команда сжатия
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
        
        log_message(f"Сжатие видео: битрейт {video_bitrate} bps, длительность {duration:.1f} сек")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Видео сжато: {new_size:.1f} МБ")
            return output_path
        else:
            if result.stderr:
                log_message(f"Ошибка FFmpeg: {result.stderr[:200]}", "ERROR")
            return None
            
    except subprocess.TimeoutExpired:
        log_message("❌ Таймаут сжатия видео", "ERROR")
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
        # Форматы для разных качеств
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
        
        # Базовые настройки yt-dlp
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
            'merge_output_format': 'mp4',
            'geo_bypass': True,
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
            log_message("📁 Использую cookies для аутентификации")
        
        with YoutubeDL(opts) as ydl:
            log_message("Получение информации о видео...")
            info = ydl.extract_info(url, download=True)
            
            if not info:
                log_message("❌ Не удалось получить информацию", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Поиск скачанного файла
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp4_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')]
                if mp4_files:
                    filename = max(mp4_files, key=os.path.getmtime)
                    log_message(f"Найден файл: {os.path.basename(filename)}")
                else:
                    log_message("❌ Файл не найден после скачивания", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:50]}... ({file_size:.1f} МБ)")
            
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
        log_message(f"Ошибка скачивания: {e}", "ERROR")
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио в MP3"""
    audio_id = hashlib.md5(f"{url}_audio".encode()).hexdigest()
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Аудио из кэша: {cached['title'][:50]}")
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
        
        # Добавляем cookies если есть
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
        
        with YoutubeDL(opts) as ydl:
            log_message("Скачивание аудио...")
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
                mp3_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
                if mp3_files:
                    filename = max(mp3_files, key=os.path.getmtime)
                    log_message(f"Найден аудиофайл: {os.path.basename(filename)}")
                else:
                    log_message("❌ MP3 файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Аудио скачано: {title[:50]}... ({file_size:.1f} МБ)")
            
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
        log_message(f"Ошибка скачивания аудио: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА ВИДЕО ====================
async def send_video_with_compress(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    """Отправка видео с автоматическим сжатием"""
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT = 49
    cache_text = " ⚡(из кэша)" if from_cache else ""
    
    try:
        # Если файл меньше лимита - отправляем сразу
        if file_size_mb <= LIMIT:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Видео отправлено ({file_size_mb:.1f} МБ)")
            return True
        
        # Сжатие видео
        status_msg = await message.answer(
            f"📦 *Сжимаю видео...*\n"
            f"Размер: {file_size_mb:.1f} МБ\n"
            f"Цель: до 48 МБ\n"
            f"⏳ Подождите 2-3 минуты",
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
                log_message(f"✅ Видео отправлено со сжатием ({new_size:.1f} МБ)")
                
                # Удаляем сжатый файл
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(
                    f"❌ *Не удалось сжать видео*\n"
                    f"Получилось {new_size:.1f} МБ\n"
                    f"Попробуйте качество ниже",
                    parse_mode=ParseMode.MARKDOWN
                )
                return False
        else:
            await status_msg.edit_text(
                "❌ *Ошибка сжатия*\n"
                "Попробуйте качество ниже (720p или 480p)",
                parse_mode=ParseMode.MARKDOWN
            )
            return False
            
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
        await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
        return False

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_keyboard(url: str):
    """Клавиатура выбора качества"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    cookies_info = check_cookies()
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    
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
    """Меню управления cookies"""
    cookies_info = check_cookies()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить cookies", callback_data="upload_cookies")],
        [InlineKeyboardButton(text="🗑️ Удалить cookies", callback_data="delete_cookies")],
        [InlineKeyboardButton(text="📊 Статус cookies", callback_data="status_cookies")]
    ])
    
    await message.answer(
        f"🍪 *Управление cookies*\n\n"
        f"{cookies_info['message']}\n\n"
        f"📌 *Как получить cookies:*\n"
        f"1. Установите расширение 'Get cookies.txt LOCALLY'\n"
        f"2. Войдите в YouTube в браузере\n"
        f"3. Нажмите на иконку расширения\n"
        f"4. Выберите 'Export cookies'\n"
        f"5. Отправьте файл сюда",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("upload_cookies"))
async def upload_cookies_command(message: types.Message):
    """Команда для загрузки cookies"""
    await message.answer(
        "📤 *Отправьте файл cookies.txt*\n\n"
        "1. Нажмите на кнопку '📎' (скрепка)\n"
        "2. Выберите 'Файл'\n"
        "3. Выберите ваш файл cookies.txt\n"
        "4. Отправьте боту",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    cookies_info = check_cookies()
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    
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
    """Обработка загруженных файлов (cookies)"""
    document = message.document
    file_name = document.file_name
    
    # Проверяем, что это файл cookies
    if file_name == "cookies.txt" or file_name.endswith(".txt"):
        try:
            status_msg = await message.answer("⏳ *Загрузка cookies файла...*", parse_mode=ParseMode.MARKDOWN)
            
            # Скачиваем файл
            file = await bot.get_file(document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            # Временный файл
            temp_path = os.path.join(TOOLS_DIR, "temp_cookies.txt")
            with open(temp_path, 'wb') as f:
                f.write(downloaded_file.getvalue())
            
            # Проверяем размер
            file_size = os.path.getsize(temp_path)
            if file_size < 100:
                await status_msg.edit_text(
                    "❌ *Файл слишком маленький*\n"
                    f"Размер: {file_size} байт\n"
                    "Нужно минимум 100 байт.\n"
                    "Убедитесь, что вы экспортировали cookies правильно.",
                    parse_mode=ParseMode.MARKDOWN
                )
                os.remove(temp_path)
                return
            
            # Сохраняем cookies
            shutil.copy2(temp_path, COOKIES_FILE)
            os.remove(temp_path)
            
            # Проверяем сохранение
            if os.path.exists(COOKIES_FILE):
                final_size = os.path.getsize(COOKIES_FILE)
                await status_msg.edit_text(
                    f"✅ *Cookies успешно загружены!*\n\n"
                    f"📊 Размер: {final_size} байт\n"
                    f"📁 Файл сохранён как: `{COOKIES_FILE}`\n\n"
                    f"Теперь YouTube видео должны скачиваться без проблем.",
                    parse_mode=ParseMode.MARKDOWN
                )
                log_message(f"✅ Cookies загружены пользователем {message.from_user.id}, размер {final_size} байт")
            else:
                await status_msg.edit_text("❌ *Ошибка сохранения cookies*", parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            log_message(f"Ошибка загрузки cookies: {e}", "ERROR")
            await message.answer(f"❌ *Ошибка загрузки:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            "❌ *Неверный файл*\n\n"
            "Отправьте файл с именем `cookies.txt`\n"
            "Используйте команду /cookies для получения инструкции.",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ОБРАБОТКА ТЕКСТА ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*\nСсылка должна начинаться с http:// или https://", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(
        "🎥 *Выберите качество:*\n\n"
        "💡 *Совет:* Для больших видео выбирайте 720p",
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
    
    # Обработка меню cookies
    if data == "upload_cookies":
        await callback.message.edit_text(
            "📤 *Загрузите cookies файл*\n\n"
            "Просто отправьте файл `cookies.txt` в этот чат.\n\n"
            "📌 *Инструкция:*\n"
            "1. Установите расширение 'Get cookies.txt LOCALLY'\n"
            "2. Войдите в YouTube\n"
            "3. Нажмите на иконку расширения\n"
            "4. Выберите 'Export cookies'\n"
            "5. Отправьте полученный файл сюда",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    if data == "delete_cookies":
        if delete_cookies():
            await callback.message.edit_text(
                "🗑️ *Cookies удалены*\n\n"
                "Вы можете загрузить новые через /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.edit_text(
                "❌ *Файл cookies не найден*\n\n"
                "Нечего удалять.",
                parse_mode=ParseMode.MARKDOWN
            )
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
    
    # Обработка скачивания видео
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
            f"⏳ *Скачиваю {quality_name}...*\n"
            f"Это может занять 1-3 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ *Не удалось скачать видео*\n\n"
                "Возможные причины:\n"
                "• Нет cookies (команда /cookies)\n"
                "• Видео удалено или приватно\n"
                "• YouTube временно блокирует\n\n"
                "Попробуйте другое качество или загрузите cookies",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        await status_msg.edit_text(f"📤 *Отправка видео...*", parse_mode=ParseMode.MARKDOWN)
        
        success = await send_video_with_compress(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.answer("❌ Ошибка отправки")
        
    elif action == "audio":
        url = parts[1]
        
        status_msg = await callback.message.edit_text(
            "⏳ *Скачиваю аудио (MP3)...*\nПодождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Не удалось скачать аудио*\n"
                "Проверьте cookies командой /cookies",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " ⚡(из кэша)" if from_cache else ""
        
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
            log_message(f"Ошибка отправки аудио: {e}", "ERROR")
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Автоматическая установка FFmpeg для Windows
    if platform.system() == "Windows":
        print("🔧 Проверка FFmpeg для Windows...")
        if not check_ffmpeg():
            print("⚠️ FFmpeg не найден, начинаю автоматическую установку...")
            if install_ffmpeg_windows():
                print("✅ FFmpeg успешно установлен!")
            else:
                print("❌ Ошибка установки FFmpeg")
        else:
            print("✅ FFmpeg уже установлен")
    else:
        # Для Linux через apt
        if not check_ffmpeg():
            print("⚠️ Установка FFmpeg через apt...")
            try:
                subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
                subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
                print("✅ FFmpeg установлен через apt")
            except:
                print("❌ Не удалось установить FFmpeg")
        else:
            print("✅ FFmpeg уже установлен")
    
    # Проверка cookies
    cookies_info = check_cookies()
    print(f"🍪 {cookies_info['message']}")
    
    # Обновление yt-dlp
    try:
        print("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        print("✅ yt-dlp обновлён")
    except Exception as e:
        print(f"⚠️ Ошибка обновления yt-dlp: {e}")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"🗜️ Папка сжатия: {os.path.abspath(COMPRESSED_DIR)}")
    print(f"🔧 Папка инструментов: {os.path.abspath(TOOLS_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("📤 Отправьте файл cookies.txt в бота для обхода блокировки YouTube")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
