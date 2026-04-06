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

def install_ffmpeg_linux():
    try:
        log_message("🚀 Установка FFmpeg...")
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        return check_ffmpeg()
    except:
        return False

def ensure_ffmpeg():
    if check_ffmpeg():
        return True
    return install_ffmpeg_linux()

# ==================== ОПТИМИЗИРОВАННОЕ СЖАТИЕ ====================
def get_video_info(file_path: str):
    """Быстрое получение информации о видео"""
    global FFPROBE_PATH
    
    if not FFPROBE_PATH:
        return None
    
    try:
        cmd = [FFPROBE_PATH, '-v', 'error', '-show_entries', 
               'format=duration,size', '-show_entries', 
               'stream=width,height,bit_rate',
               '-of', 'json', file_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return None
    except:
        return None

def compress_video_fast(input_path: str, target_size_mb: int = 48) -> str:
    """
    МАКСИМАЛЬНО БЫСТРОЕ СЖАТИЕ ВИДЕО
    Использует ultrafast preset и агрессивное уменьшение разрешения
    """
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        log_message("❌ FFmpeg не найден", "ERROR")
        return None
    
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        
        # Если видео уже меньше 50 МБ - не сжимаем
        if original_size <= 49:
            return input_path
        
        # Получаем информацию о видео
        info = get_video_info(input_path)
        
        duration = 60.0
        width = 1280
        height = 720
        
        if info:
            if 'format' in info and 'duration' in info['format']:
                duration = float(info['format']['duration'])
            
            if 'streams' in info:
                for stream in info['streams']:
                    if stream.get('codec_type') == 'video':
                        width = stream.get('width', 1280)
                        height = stream.get('height', 720)
                        break
        
        # Определяем целевое разрешение (чем больше сжатие, тем меньше разрешение)
        compression_ratio = original_size / target_size_mb
        
        if compression_ratio > 5:  # Очень большое видео
            target_width = 426
            target_height = 240
            preset = 'ultrafast'
            crf = 35
        elif compression_ratio > 3:  # Большое видео
            target_width = 640
            target_height = 360
            preset = 'ultrafast'
            crf = 32
        elif compression_ratio > 2:  # Среднее видео
            target_width = 854
            target_height = 480
            preset = 'superfast'
            crf = 30
        else:  # Немного больше лимита
            target_width = 1280
            target_height = 720
            preset = 'veryfast'
            crf = 28
        
        # Сохраняем пропорции
        if width > height:
            target_height = int(target_width * height / width)
        else:
            target_width = int(target_height * width / height)
        
        # Округляем до четного
        target_width = target_width if target_width % 2 == 0 else target_width + 1
        target_height = target_height if target_height % 2 == 0 else target_height + 1
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_fast.mp4")
        
        # МАКСИМАЛЬНО БЫСТРАЯ КОМАНДА СЖАТИЯ
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-vf', f'scale={target_width}:{target_height}',
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', str(crf),
            '-c:a', 'aac',
            '-b:a', '96k',
            '-movflags', '+faststart',
            '-threads', '4',  # Параллельная обработка
            '-y', output_path
        ]
        
        log_message(f"⚡ Быстрое сжатие: {original_size:.1f} МБ -> {target_width}x{target_height}, preset={preset}, crf={crf}")
        
        start_time = datetime.now()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        elapsed = (datetime.now() - start_time).seconds
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато за {elapsed} сек: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            
            # Если всё ещё больше 50 МБ - сжимаем ещё раз с более низким качеством
            if new_size > 49:
                log_message(f"⚠️ Повторное сжатие...")
                cmd2 = [
                    FFMPEG_PATH, '-i', output_path,
                    '-vf', f'scale={target_width//2}:{target_height//2}',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '38',
                    '-c:a', 'aac',
                    '-b:a', '64k',
                    '-movflags', '+faststart',
                    '-threads', '4',
                    '-y', output_path.replace('.mp4', '_2.mp4')
                ]
                
                result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
                if result2.returncode == 0:
                    os.remove(output_path)
                    output_path = output_path.replace('.mp4', '_2.mp4')
                    new_size = os.path.getsize(output_path) / (1024 * 1024)
                    log_message(f"✅ Повторное сжатие: {new_size:.1f} МБ")
            
            return output_path
        else:
            log_message(f"❌ Ошибка сжатия", "ERROR")
            return None
            
    except subprocess.TimeoutExpired:
        log_message("❌ Сжатие превысило лимит времени", "ERROR")
        return None
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== COOKIES ====================
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
        return True
    except:
        return False

def delete_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
            return True
        return False
    except:
        return False

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
            'socket_timeout': 30,
            'retries': 5,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
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
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
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
            f"⚡ *Быстрое сжатие...*\n"
            f"Размер: {file_size_mb:.1f} МБ\n"
            f"⏳ Обычно 30-60 секунд",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        compressed_path = await loop.run_in_executor(None, compress_video_fast, file_path, 48)
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:80]}*{cache_text} ⚡\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(f"❌ *Не удалось сжать до 50 МБ*\nПопробуйте качество ниже", parse_mode=ParseMode.MARKDOWN)
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
    ffmpeg_status = "✅" if FFMPEG_PATH else "❌"
    
    await message.answer(
        f"🎬 *Видео-Бот (быстрое сжатие)*\n\n"
        f"📹 Отправьте ссылку на YouTube видео\n\n"
        f"*Статус:*\n"
        f"🎬 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_info['message']}\n\n"
        f"⚡ *Сжатие занимает 30-60 секунд!*\n\n"
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
    ffmpeg_status = "✅" if FFMPEG_PATH else "❌"
    
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
        "🎥 *Выберите качество:*\n\n⚡ Сжатие видео занимает 30-60 секунд!",
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
        
        await status_msg.edit_text(f"⚡ *Сжатие видео...*", parse_mode=ParseMode.MARKDOWN)
        
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
    print("🤖 БОТ ЗАПУЩЕН (БЫСТРОЕ СЖАТИЕ)")
    print("=" * 60)
    
    ensure_ffmpeg()
    
    if FFMPEG_PATH:
        print(f"✅ FFmpeg готов: {FFMPEG_PATH}")
    else:
        print("❌ FFmpeg не установлен")
    
    cookies_info = check_cookies()
    print(f"🍪 {cookies_info['message']}")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 60)
    print("⚡ Сжатие видео: 30-60 секунд (в 10-20 раз быстрее!)")
    print("✅ БОТ ГОТОВ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
