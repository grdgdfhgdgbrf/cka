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

# ID администратора (замените на свой Telegram ID)
ADMIN_IDS = [5356400377]  # Добавьте сюда ваш ID

DOWNLOAD_DIR = "downloads"
COMPRESSED_DIR = "compressed"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"
TOOLS_DIR = "tools"
COOKIES_FILE = "cookies.txt"
STATS_FILE = "stats.json"

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR, TOOLS_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

FFMPEG_PATH = None
FFPROBE_PATH = None

# ==================== СТАТИСТИКА ====================
def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'total_users': 0, 'total_downloads': 0, 'total_size_mb': 0}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except:
        pass

stats = load_stats()

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
log_message(f"📦 Загружено {len(video_cache)} записей кэша")

# ==================== УСТАНОВКА FFMPEG ====================
def check_ffmpeg():
    global FFMPEG_PATH, FFPROBE_PATH
    
    system_ffmpeg = shutil.which("ffmpeg")
    system_ffprobe = shutil.which("ffprobe")
    
    if system_ffmpeg and system_ffprobe:
        FFMPEG_PATH = system_ffmpeg
        FFPROBE_PATH = system_ffprobe
        log_message(f"✅ FFmpeg найден: {FFMPEG_PATH}")
        return True
    
    local_ffmpeg = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffmpeg")
    local_ffprobe = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffprobe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        FFMPEG_PATH = local_ffmpeg
        FFPROBE_PATH = local_ffprobe
        os.chmod(FFMPEG_PATH, 0o755)
        os.chmod(FFPROBE_PATH, 0o755)
        log_message("✅ FFmpeg найден локально")
        return True
    
    log_message("❌ FFmpeg не найден", "WARNING")
    return False

def install_ffmpeg_linux():
    try:
        log_message("🚀 Установка FFmpeg...")
        subprocess.run(['apt-get', 'update'], capture_output=True, timeout=60)
        subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, timeout=120)
        return check_ffmpeg()
    except Exception as e:
        log_message(f"Ошибка установки: {e}", "ERROR")
        return False

def ensure_ffmpeg():
    if check_ffmpeg():
        return True
    if install_ffmpeg_linux():
        return True
    return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video_fast(input_path: str, target_size_mb: int = 48) -> str:
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        return None
    
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        
        if original_size <= target_size_mb:
            log_message(f"✅ Видео уже {original_size:.1f} МБ, сжатие не требуется")
            return input_path
        
        # Получаем длительность
        cmd_duration = [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
        result = subprocess.run(cmd_duration, capture_output=True, text=True, timeout=10)
        duration = float(result.stdout.strip()) if result.stdout else 60
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(500000, min(video_bitrate, 2500000))
        
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Быстрое сжатие
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-b:v', f'{video_bitrate}',
            '-maxrate', f'{int(video_bitrate * 1.5)}',
            '-bufsize', f'{video_bitrate * 2}',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-threads', '2',
            '-y', output_path
        ]
        
        log_message(f"🗜️ Сжатие: {original_size:.1f} МБ -> {target_size_mb} МБ")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {original_size:.1f} МБ -> {new_size:.1f} МБ")
            return output_path
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
            log_message(f"📦 Из кэша: {cached['title'][:40]}")
            return cached['path'], cached['title'], True
    
    # Соответствие качества формату
    quality_formats = {
        "144": 'worst[height<=144]',
        "240": 'best[height<=240]',
        "360": 'best[height<=360]',
        "480": 'best[height<=480]',
        "720": 'best[height<=720]',
        "1080": 'best[height<=1080]',
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
    
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
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
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:40]} ({file_size:.1f} МБ)")
            
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
                caption=f"✅ *{title[:60]}*\n\n{cache_icon} Качество: `{quality}p`\n💾 Размер: `{file_size_mb:.1f} МБ`",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
        
        status_msg = await message.answer(
            f"🔄 *Сжатие видео*\n\n"
            f"📊 Исходный размер: `{file_size_mb:.1f} МБ`\n"
            f"🎯 Целевой размер: `< 50 МБ`\n"
            f"⏳ Пожалуйста, подождите...",
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
                    caption=f"✅ *{title[:60]}*\n\n{cache_icon} Качество: `{quality}p`\n🗜️ Сжато: `{file_size_mb:.1f} МБ` → `{new_size:.1f} МБ`",
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
                    f"📊 Размер после сжатия: `{new_size:.1f} МБ`\n"
                    f"💡 Попробуйте выбрать качество ниже",
                    parse_mode=ParseMode.MARKDOWN
                )
                return False
        else:
            await status_msg.edit_text(
                f"❌ *Ошибка сжатия*\n\n"
                f"💡 Попробуйте выбрать качество ниже или повторите позже",
                parse_mode=ParseMode.MARKDOWN
            )
            return False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
        return False

# ==================== АДМИН-ПАНЕЛЬ ====================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton(text="🗑️ Очистить кэш", callback_data="admin_clear_cache")],
        [InlineKeyboardButton(text="📦 Размер кэша", callback_data="admin_cache_size"),
         InlineKeyboardButton(text="🔄 Перезапустить", callback_data="admin_restart")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_broadcast"),
         InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])

async def send_admin_panel(message: types.Message):
    keyboard = get_admin_keyboard()
    await message.answer(
        f"👑 *Админ-панель*\n\n"
        f"Добро пожаловать в панель управления ботом!\n\n"
        f"📊 *Статистика:*\n"
        f"• Пользователей: `{stats['total_users']}`\n"
        f"• Скачиваний: `{stats['total_downloads']}`\n"
        f"• Скачано: `{stats['total_size_mb']:.1f} МБ`\n"
        f"• В кэше: `{len(video_cache)}` файлов",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== КЛАВИАТУРА ВЫБОРА КАЧЕСТВА ====================
def get_quality_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # Обновляем статистику
    if user_id not in stats.get('users', []):
        stats['users'] = stats.get('users', [])
        stats['users'].append(user_id)
        stats['total_users'] = len(stats['users'])
        save_stats(stats)
    
    cookies_status = "✅" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100 else "❌"
    ffmpeg_status = "✅" if FFMPEG_PATH else "❌"
    
    await message.answer(
        f"🎬 *VideoBot - Скачивание видео*\n\n"
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        f"Я помогу скачать видео с YouTube в любом качестве!\n\n"
        f"📹 *Как пользоваться:*\n"
        f"• Просто отправьте мне ссылку на видео\n"
        f"• Выберите нужное качество\n"
        f"• Получите готовый файл\n\n"
        f"⚙️ *Статус:*\n"
        f"• FFmpeg: {ffmpeg_status}\n"
        f"• Cookies: {cookies_status}\n\n"
        f"💡 *Совет:* Если видео не скачивается, используйте команду /cookies",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        f"📖 *Помощь*\n\n"
        f"🔹 *Как скачать видео:*\n"
        f"1. Скопируйте ссылку с YouTube\n"
        f"2. Отправьте её боту\n"
        f"3. Выберите качество\n"
        f"4. Дождитесь обработки\n\n"
        f"🔹 *Доступные команды:*\n"
        f"/start - Главное меню\n"
        f"/help - Эта справка\n"
        f"/cookies - Загрузить cookies\n"
        f"/stats - Статистика\n"
        f"/clear - Очистить кэш\n"
        f"/admin - Админ-панель (только для админов)\n\n"
        f"🔹 *Поддерживаемые качества:*\n"
        f"144p, 240p, 360p, 480p, 720p, 1080p, Лучшее\n\n"
        f"🔹 *Ограничения:*\n"
        f"• Максимальный размер видео: 50 МБ\n"
        f"• Большие видео автоматически сжимаются",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_cmd(message: types.Message):
    await message.answer(
        f"🍪 *Инструкция по получению cookies*\n\n"
        f"📌 *Шаг 1:* Установите расширение\n"
        f"Chrome: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)\n\n"
        f"📌 *Шаг 2:* Войдите в YouTube\n\n"
        f"📌 *Шаг 3:* Нажмите на иконку расширения и выберите 'Export cookies'\n\n"
        f"📌 *Шаг 4:* Отправьте полученный файл сюда\n\n"
        f"📤 *Просто отправьте файл cookies.txt боту*",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    await message.answer(
        f"📊 *Статистика бота*\n\n"
        f"👥 Пользователей: `{stats.get('total_users', 0)}`\n"
        f"📥 Всего скачиваний: `{stats.get('total_downloads', 0)}`\n"
        f"💾 Скачано данных: `{stats.get('total_size_mb', 0):.1f} МБ`\n"
        f"📦 В кэше: `{len(video_cache)}` видео\n"
        f"💿 Занято кэшем: `{total_size/(1024*1024):.1f} МБ`\n"
        f"🎬 FFmpeg: `{'✅' if FFMPEG_PATH else '❌'}`\n"
        f"🍪 Cookies: `{'✅' if os.path.exists(COOKIES_FILE) else '❌'}`",
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
    await message.answer(
        f"🗑️ *Кэш очищен*\n\n"
        f"Удалено файлов: `{deleted}`",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await send_admin_panel(message)
    else:
        await message.answer("❌ У вас нет доступа к админ-панели", parse_mode=ParseMode.MARKDOWN)

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
                f"📊 Размер: `{file_size} байт`\n"
                f"🍪 Теперь YouTube видео будут скачиваться без проблем",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Cookies загружены пользователем {message.from_user.id}")
            
        except Exception as e:
            await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(
            f"❌ *Неверный файл*\n\n"
            f"Пожалуйста, отправьте файл с именем `cookies.txt`\n"
            f"Команда /cookies - инструкция по получению",
            parse_mode=ParseMode.MARKDOWN
        )

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            f"❌ *Неверная ссылка*\n\n"
            f"Пожалуйста, отправьте корректную ссылку на видео YouTube\n"
            f"Пример: `https://youtu.be/...` или `https://www.youtube.com/watch?v=...`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        f"🎥 *Выберите качество видео*\n\n"
        f"📹 Видео будет скачано в выбранном качестве\n"
        f"⚡ Большие видео автоматически сжимаются до 50 МБ",
        reply_markup=get_quality_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТКА КНОПОК ====================
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    if data == "cancel":
        await callback.message.edit_text("❌ *Операция отменена*", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    # Админ-панель
    if data.startswith("admin_"):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа")
            return
        
        if data == "admin_stats":
            total_size = 0
            for info in video_cache.values():
                if os.path.exists(info.get('path', '')):
                    total_size += os.path.getsize(info['path'])
            
            await callback.message.edit_text(
                f"📊 *Статистика бота*\n\n"
                f"👥 Пользователей: `{stats.get('total_users', 0)}`\n"
                f"📥 Скачиваний: `{stats.get('total_downloads', 0)}`\n"
                f"💾 Скачано: `{stats.get('total_size_mb', 0):.1f} МБ`\n"
                f"📦 В кэше: `{len(video_cache)}`\n"
                f"💿 Кэш: `{total_size/(1024*1024):.1f} МБ`",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            
        elif data == "admin_clear_cache":
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
            await callback.message.edit_text(f"🗑️ *Очищено {deleted} файлов*", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            
        elif data == "admin_cache_size":
            total_size = 0
            for info in video_cache.values():
                if os.path.exists(info.get('path', '')):
                    total_size += os.path.getsize(info['path'])
            await callback.message.edit_text(
                f"📦 *Размер кэша*\n\n"
                f"Файлов в кэше: `{len(video_cache)}`\n"
                f"Занято места: `{total_size/(1024*1024):.1f} МБ`",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            
        elif data == "admin_logs":
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    last_lines = lines[-50:] if len(lines) > 50 else lines
                    log_text = "".join(last_lines)
                    await callback.message.edit_text(
                        f"📋 *Последние логи*\n\n```\n{log_text[:3000]}\n```",
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                await callback.message.edit_text("Логов пока нет", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            
        elif data == "admin_close":
            await callback.message.delete()
            await callback.answer()
            
        return
    
    # Скачивание видео
    parts = data.split("_", 2)
    if len(parts) < 2:
        await callback.answer("Ошибка")
        return
    
    action = parts[0]
    
    if action == "vid":
        quality = parts[1]
        url = parts[2]
        
        quality_name = quality
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачивание видео*\n\n"
            f"📹 Качество: `{quality_name}p`\n"
            f"⏱️ Пожалуйста, подождите...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                f"❌ *Ошибка скачивания*\n\n"
                f"Возможные причины:\n"
                f"• Нет cookies (команда /cookies)\n"
                f"• Видео недоступно\n"
                f"• Неподдерживаемое качество\n\n"
                f"💡 Попробуйте другое качество",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        # Обновляем статистику
        stats['total_downloads'] = stats.get('total_downloads', 0) + 1
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        stats['total_size_mb'] = stats.get('total_size_mb', 0) + file_size_mb
        save_stats(stats)
        
        await status_msg.edit_text(
            f"📤 *Отправка видео*\n\n"
            f"📹 `{title[:50]}...`\n"
            f"📊 Размер: `{file_size_mb:.1f} МБ`",
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
            f"⏳ *Скачивание аудио*\n\n"
            f"🎵 Формат: MP3\n"
            f"⏱️ Пожалуйста, подождите...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text(
                f"❌ *Ошибка скачивания аудио*\n\n"
                f"💡 Попробуйте загрузить cookies: /cookies",
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
                caption=f"✅ *{title[:60]}*\n\n{cache_icon} Формат: `MP3`\n💾 Размер: `{file_size:.1f} МБ`",
                parse_mode=ParseMode.MARKDOWN
            )
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🎬 ВИДЕО-БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    if ensure_ffmpeg():
        print("✅ FFmpeg готов")
    else:
        print("❌ FFmpeg не установлен")
    
    cookies_status = "✅" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100 else "❌"
    print(f"🍪 Cookies: {cookies_status}")
    print(f"👥 Пользователей: {stats.get('total_users', 0)}")
    print(f"📥 Всего скачиваний: {stats.get('total_downloads', 0)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
