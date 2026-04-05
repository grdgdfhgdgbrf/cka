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

# ==================== ДИАГНОСТИКА COOKIES ====================
def diagnose_cookies():
    """Диагностика cookies файла"""
    if not os.path.exists(COOKIES_FILE):
        return "❌ Файл cookies.txt не найден"
    
    try:
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        valid_lines = 0
        has_youtube = False
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                valid_lines += 1
                if '.youtube.com' in line or 'youtube.com' in line:
                    has_youtube = True
        
        if valid_lines == 0:
            return "❌ Cookies файл пуст или содержит только комментарии"
        
        if not has_youtube:
            return f"⚠️ В cookies нет записей для YouTube (найдено {valid_lines} записей)"
        
        return f"✅ Cookies валидны: {valid_lines} записей, YouTube найден"
        
    except Exception as e:
        return f"❌ Ошибка чтения cookies: {e}"

def check_cookies() -> bool:
    """Проверка наличия и валидности cookies"""
    if not os.path.exists(COOKIES_FILE):
        log_message("❌ Cookies файл не найден", "WARNING")
        return False
    
    try:
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем что есть данные для YouTube
        if '.youtube.com' in content or 'youtube.com' in content:
            log_message("✅ Cookies файл найден и содержит YouTube данные")
            return True
        else:
            log_message("⚠️ Cookies файл не содержит данных для YouTube", "WARNING")
            return False
            
    except Exception as e:
        log_message(f"❌ Ошибка проверки cookies: {e}", "ERROR")
        return False

# ==================== ОПРЕДЕЛЕНИЕ ПУТЕЙ ====================
def get_ffmpeg_path():
    ffmpeg_paths = [
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    
    for path in ffmpeg_paths:
        if path and os.path.exists(path):
            return path
    return None

def get_ffprobe_path():
    ffprobe_paths = [
        shutil.which("ffprobe"),
        shutil.which("ffprobe.exe"),
        "/usr/bin/ffprobe",
        "/usr/local/bin/ffprobe",
    ]
    
    for path in ffprobe_paths:
        if path and os.path.exists(path):
            return path
    return None

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
def check_ffmpeg() -> bool:
    return get_ffmpeg_path() is not None

def install_ffmpeg():
    try:
        log_message("🚀 Установка FFmpeg...")
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        log_message("✅ FFmpeg установлен")
        return True
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def get_video_duration(file_path: str) -> float:
    try:
        ffprobe_path = get_ffprobe_path()
        if not ffprobe_path:
            return 60.0
        
        cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 60.0
    except:
        return 60.0

def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    try:
        ffmpeg_path = get_ffmpeg_path()
        if not ffmpeg_path:
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
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== ПРЯМОЕ СКАЧИВАНИЕ С COOKIES ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео с YouTube используя cookies"""
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    # Проверка кэша
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:50]}")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {url[:50]}... | {quality}")
    
    # Получаем абсолютный путь к cookies
    cookies_abs_path = os.path.abspath(COOKIES_FILE)
    
    # Проверяем cookies перед скачиванием
    cookies_exist = os.path.exists(cookies_abs_path)
    if cookies_exist:
        log_message(f"🍪 Использую cookies: {cookies_abs_path}")
        # Читаем первые несколько байт для диагностики
        try:
            with open(cookies_abs_path, 'r') as f:
                first_line = f.readline().strip()
                log_message(f"🍪 Первая строка cookies: {first_line[:100]}")
        except:
            pass
    else:
        log_message(f"⚠️ Cookies не найдены по пути: {cookies_abs_path}", "WARNING")
    
    try:
        # Форматы качества
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
        
        # Базовые настройки
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
        }
        
        # Добавляем cookies ТОЛЬКО если файл существует и не пустой
        if cookies_exist:
            try:
                # Проверяем что файл не пустой
                if os.path.getsize(cookies_abs_path) > 100:
                    opts['cookiefile'] = cookies_abs_path
                    log_message("🍪 Cookies добавлены в настройки yt-dlp")
                else:
                    log_message("⚠️ Cookies файл слишком маленький, игнорирую", "WARNING")
            except Exception as e:
                log_message(f"⚠️ Ошибка при добавлении cookies: {e}", "WARNING")
        
        # Пробуем скачать
        with YoutubeDL(opts) as ydl:
            log_message("📡 Получение информации о видео...")
            
            # Сначала получаем информацию (без скачивания)
            try:
                info = ydl.extract_info(url, download=False)
                if not info:
                    log_message("❌ Не удалось получить информацию", "ERROR")
                    return None, None, False
                
                title = info.get('title', 'video')
                duration = info.get('duration', 0)
                log_message(f"📹 Видео найдено: {title[:50]} (длит: {duration} сек)")
                
                # Если информация получена - скачиваем
                log_message("⬇️ Начинаю скачивание...")
                ydl.download([url])
                
            except Exception as e:
                error_msg = str(e)
                log_message(f"❌ Ошибка yt-dlp: {error_msg}", "ERROR")
                
                # Если ошибка связана с cookies, пробуем без них
                if 'cookies' in error_msg.lower() or '403' in error_msg:
                    log_message("🔄 Пробую скачать без cookies...")
                    opts.pop('cookiefile', None)
                    with YoutubeDL(opts) as ydl2:
                        info = ydl2.extract_info(url, download=True)
                        title = info.get('title', 'video')
                else:
                    return None, None, False
            
            title = info.get('title', 'video')
            if not title:
                title = 'video'
            
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
                    log_message(f"📁 Найден файл: {os.path.basename(filename)}")
                else:
                    log_message("❌ Файл не найден", "ERROR")
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
        log_message(f"❌ Критическая ошибка: {e}", "ERROR")
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
        cookies_abs_path = os.path.abspath(COOKIES_FILE)
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
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
        
        if os.path.exists(cookies_abs_path) and os.path.getsize(cookies_abs_path) > 100:
            opts['cookiefile'] = cookies_abs_path
        
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
        log_message(f"Ошибка аудио: {e}", "ERROR")
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
            log_message(f"✅ Отправлено ({file_size_mb:.1f} МБ)")
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
                log_message(f"✅ Отправлено со сжатием ({new_size:.1f} МБ)")
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
    cookies_status = check_cookies()
    await message.answer(
        f"🎬 *Видео-Бот*\n\n"
        f"📹 Отправьте ссылку на YouTube\n\n"
        f"🍪 Cookies: {'✅' if cookies_status else '❌'}\n\n"
        f"*Команды:*\n"
        f"/cookies - Диагностика cookies\n"
        f"/stats - Статистика\n"
        f"/clear - Очистить кэш\n"
        f"/log - Логи",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_cmd(message: types.Message):
    """Диагностика cookies"""
    diagnosis = diagnose_cookies()
    
    # Показываем путь к файлу
    abs_path = os.path.abspath(COOKIES_FILE)
    
    await message.answer(
        f"🍪 *Диагностика cookies*\n\n"
        f"📁 Путь: `{abs_path}`\n"
        f"📊 Статус: {diagnosis}\n\n"
        f"*Как получить cookies:*\n"
        f"1. Установите расширение 'Get cookies.txt LOCALLY'\n"
        f"2. Войдите в YouTube\n"
        f"3. Нажмите на иконку расширения → Export\n"
        f"4. Сохраните файл как `cookies.txt`\n"
        f"5. Поместите в папку с ботом\n\n"
        f"*Проверка:*\n"
        f"`cat cookies.txt | head -5`",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("log"))
async def log_cmd(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            log_text = "".join(last_lines)
            await message.answer(f"📋 *Логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Логов нет")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    cookies_status = "✅" if check_cookies() else "❌"
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🗜️ FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_status}",
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

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Диагностика cookies перед скачиванием
    cookies_diagnosis = diagnose_cookies()
    log_message(f"🍪 {cookies_diagnosis}")
    
    await message.answer(
        f"🎥 *Выберите качество:*\n\n"
        f"🍪 {cookies_diagnosis}\n\n"
        f"💡 Если видео не скачивается - используйте /cookies",
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
            f"⏳ *Скачиваю {quality_name}...*\nЭто может занять 1-3 минуты",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Не удалось скачать видео*\n\n"
                "Проверьте cookies командой /cookies\n\n"
                "Возможные причины:\n"
                "• Нет или устаревшие cookies\n"
                "• YouTube блокирует запросы\n"
                "• Видео недоступно",
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
    
    # FFmpeg
    if not check_ffmpeg():
        print("⚠️ Установка FFmpeg...")
        install_ffmpeg()
    else:
        print("✅ FFmpeg готов")
    
    # Диагностика cookies
    print(f"🍪 {diagnose_cookies()}")
    print(f"📁 Путь к cookies: {os.path.abspath(COOKIES_FILE)}")
    
    # Обновление yt-dlp
    try:
        print("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        print("✅ yt-dlp обновлён")
    except:
        pass
    
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
