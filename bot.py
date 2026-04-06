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
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"
ADMIN_IDS = [5356400377]  # ID администраторов (можно добавить несколько)

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
    if install_ffmpeg():
        return True
    log_message("❌ FFmpeg не установлен", "ERROR")
    return False

# ==================== БЫСТРОЕ СЖАТИЕ (УЛУЧШЕННОЕ) ====================
def get_hardware_acceleration():
    if not FFMPEG_PATH:
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

def get_video_duration(file_path: str) -> float:
    if not FFPROBE_PATH:
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

def compress_video_fast(input_path: str, target_size_mb: int = 48) -> str:
    """Быстрое сжатие видео (10-30 секунд)"""
    if not FFMPEG_PATH:
        return None

    original_size = os.path.getsize(input_path) / (1024 * 1024)
    if original_size <= target_size_mb:
        return input_path  # не нужно сжимать

    duration = get_video_duration(input_path)
    if duration <= 0:
        duration = 60

    # Рассчитываем битрейт
    target_bits = target_size_mb * 8 * 1024 * 1024
    video_bitrate = int(target_bits / duration)
    video_bitrate = max(500000, min(video_bitrate, 3000000))  # 0.5 - 3 Mbps

    base_name = os.path.basename(input_path)
    name_without_ext = os.path.splitext(base_name)[0]
    output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")

    hw = get_hardware_acceleration()

    # Базовые параметры: копируем аудио, ultrafast preset
    if hw == 'h264_nvenc':
        cmd = [FFMPEG_PATH, '-i', input_path,
               '-c:v', 'h264_nvenc', '-preset', 'p1',
               '-b:v', f'{video_bitrate}',
               '-maxrate', f'{int(video_bitrate*1.5)}',
               '-bufsize', f'{video_bitrate*2}',
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

    try:
        log_message(f"⚡ Сжатие: {original_size:.1f} МБ -> {target_size_mb} МБ, битрейт {video_bitrate}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"Ошибка сжатия: {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        log_message("❌ Таймаут сжатия")
        return None
    except Exception as e:
        log_message(f"Ошибка: {e}")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    """quality: 144, 240, 360, 480, 720, 1080, best"""
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            return cached['path'], cached['title'], True

    # Формат в зависимости от качества (высота)
    height_map = {
        "144": 144, "240": 240, "360": 360,
        "480": 480, "720": 720, "1080": 1080, "best": 2160
    }
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
        'http_headers': {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
    }
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts['cookiefile'] = COOKIES_FILE

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            # поиск файла
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
            video_cache[video_id] = {'path': filename, 'title': title, 'quality': quality,
                                      'url': url, 'date': datetime.now().isoformat(), 'size_mb': file_size}
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
        'http_headers': {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
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
        await message.answer_video(video, caption=f"✅ *{title[:70]}*{cache_str}\n🎬 Качество: {quality}p | 📦 {file_size:.1f} МБ", parse_mode=ParseMode.MARKDOWN)
        return True
    # Сжатие
    status = await message.answer("⚡ *Сжимаю видео...*\n⏳ Это займёт 10–30 секунд", parse_mode=ParseMode.MARKDOWN)
    loop = asyncio.get_event_loop()
    compressed = await loop.run_in_executor(None, compress_video_fast, file_path, 48)
    if compressed and os.path.exists(compressed):
        new_size = os.path.getsize(compressed) / (1024 * 1024)
        if new_size <= limit:
            await status.delete()
            video = FSInputFile(compressed)
            await message.answer_video(video, caption=f"✅ *{title[:70]}*{cache_str} 🗜️\n🎬 {quality}p | {new_size:.1f} МБ (было {file_size:.1f} МБ)", parse_mode=ParseMode.MARKDOWN)
            os.remove(compressed)
            return True
        else:
            await status.edit_text(f"⚠️ *Не удалось сжать до 50 МБ* (получилось {new_size:.1f} МБ).\nПопробуйте качество ниже.")
            return False
    else:
        await status.edit_text("❌ *Ошибка сжатия*. Попробуйте выбрать качество ниже.")
        return False

# ==================== АДМИН-ПАНЕЛЬ ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 *Доступ запрещён*. Вы не администратор.", parse_mode=ParseMode.MARKDOWN)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🗑️ Очистить кэш", callback_data="admin_clear")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🍪 Статус cookies", callback_data="admin_cookies")],
        [InlineKeyboardButton(text="⚙️ Перезапустить бота", callback_data="admin_restart")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await message.answer("🔐 *Админ-панель*\nВыберите действие:", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def admin_stats(message):
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    ffmpeg_status = "✅" if FFMPEG_PATH else "❌"
    cookies_ok = "✅" if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100 else "❌"
    text = (f"📊 *Статистика бота*\n\n"
            f"📁 В кэше: {len(video_cache)} видео\n"
            f"💾 Занято: {total_size:.1f} МБ\n"
            f"🎬 FFmpeg: {ffmpeg_status}\n"
            f"🍪 Cookies: {cookies_ok}\n"
            f"🖥️ Сервер: {platform.system()} {platform.machine()}")
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
    await message.answer(f"🗑️ *Очищено {deleted} файлов*", parse_mode=ParseMode.MARKDOWN)

async def admin_logs(message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()[-30:]
            log_text = ''.join(lines)
            await message.answer(f"📜 *Последние логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Лог-файл не найден.")

async def admin_cookies_status(message):
    if os.path.exists(COOKIES_FILE):
        size = os.path.getsize(COOKIES_FILE)
        await message.answer(f"🍪 *Cookies*: файл найден, размер {size} байт.\n✅ Используется при скачивании.", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("🍪 *Cookies*: файл не найден.\n📤 Загрузите cookies.txt через /cookies", parse_mode=ParseMode.MARKDOWN)

async def admin_restart(message):
    await message.answer("🔄 *Перезапуск бота...*", parse_mode=ParseMode.MARKDOWN)
    # Сохраняем кэш перед выходом
    save_cache(video_cache)
    # Перезапуск (в реальном коде можно использовать sys.exit, но в данном контексте просто выходим)
    os._exit(0)

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
         InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте ссылку на YouTube видео, и я скачаю его в нужном качестве.\n\n"
        "⚡ *Особенности:*\n"
        "• Быстрое сжатие видео до 50 МБ (10-30 секунд)\n"
        "• Выбор качества 144p → 1080p\n"
        "• Кэширование – повторные видео мгновенно\n"
        "• Аудио в MP3\n\n"
        "📥 *Как получить cookies?* /cookies\n"
        "🔧 *Админ-панель* – доступна только администраторам.\n\n"
        "👇 *Просто отправьте ссылку!*",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_help(message: types.Message):
    await message.answer(
        "🍪 *Инструкция по cookies*\n\n"
        "1. Установите расширение для браузера *Get cookies.txt LOCALLY*.\n"
        "2. Войдите в свой аккаунт YouTube.\n"
        "3. Нажмите на иконку расширения и выберите *Export cookies*.\n"
        "4. Сохраните файл как `cookies.txt`.\n"
        "5. Отправьте этот файл боту (просто перетащите в чат).\n\n"
        "✅ После загрузки cookies бот сможет скачивать любые видео без блокировок.",
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
            await status.edit_text(f"✅ *Cookies загружены!* Размер: {size} байт.", parse_mode=ParseMode.MARKDOWN)
            log_message(f"Cookies загружены пользователем {message.from_user.id}")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    else:
        await message.answer("❌ Пожалуйста, отправьте файл с именем `cookies.txt`", parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео* (http:// или https://)", parse_mode=ParseMode.MARKDOWN)
        return
    await message.answer("🎥 *Выберите качество видео:*", reply_markup=get_quality_keyboard(url), parse_mode=ParseMode.MARKDOWN)

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
        elif data == "admin_logs":
            await admin_logs(call.message)
        elif data == "admin_cookies":
            await admin_cookies_status(call.message)
        elif data == "admin_restart":
            await admin_restart(call.message)
        elif data == "admin_close":
            await call.message.delete()
        await call.answer()
        return

    # Обработка видео/аудио
    parts = data.split("_", 2)
    if len(parts) < 2:
        await call.answer("Ошибка")
        return
    action = parts[0]
    if action == "vid":
        quality = parts[1]   # 144, 240, 360, 480, 720, 1080, best
        url = parts[2]
        quality_name = quality if quality != "best" else "лучшее"
        status_msg = await call.message.edit_text(f"⏳ *Скачиваю {quality_name}p...*\nПожалуйста, подождите.", parse_mode=ParseMode.MARKDOWN)
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка скачивания*\nВозможно, нужны cookies. Отправьте /cookies для инструкции.", parse_mode=ParseMode.MARKDOWN)
            await call.answer()
            return
        await status_msg.edit_text("📤 *Отправляю видео...*", parse_mode=ParseMode.MARKDOWN)
        success = await send_video_with_compress(call.message, file_path, title, quality_name, from_cache)
        if success:
            await status_msg.delete()
            await call.answer("✅ Готово!")
        else:
            await call.answer("❌ Ошибка при отправке")
    elif action == "audio":
        url = parts[1]
        status_msg = await call.message.edit_text("⏳ *Скачиваю аудио...*", parse_mode=ParseMode.MARKDOWN)
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        if not file_path:
            await status_msg.edit_text("❌ *Не удалось скачать аудио*", parse_mode=ParseMode.MARKDOWN)
            await call.answer()
            return
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        audio = FSInputFile(file_path)
        await call.message.answer_audio(audio, caption=f"✅ *{title[:70]}*{' 📀 (кэш)' if from_cache else ''}\n🎵 MP3 | {file_size:.1f} МБ", parse_mode=ParseMode.MARKDOWN)
        await status_msg.delete()
        await call.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🎬 ВИДЕО-БОТ ЗАПУЩЕН")
    print("=" * 60)
    if ensure_ffmpeg():
        hw = get_hardware_acceleration()
        print(f"✅ FFmpeg готов, ускорение: {hw}")
    else:
        print("❌ FFmpeg не установлен, сжатие может не работать")
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"👥 Администраторы: {ADMIN_IDS}")
    print("=" * 60)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
