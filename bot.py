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
        log_message(f"✅ FFmpeg найден: {FFMPEG_PATH}")
        return True
    
    local_ffmpeg = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffmpeg")
    local_ffprobe = os.path.join(TOOLS_DIR, "ffmpeg", "bin", "ffprobe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        FFMPEG_PATH = local_ffmpeg
        FFPROBE_PATH = local_ffprobe
        os.chmod(FFMPEG_PATH, 0o755)
        os.chmod(FFPROBE_PATH, 0o755)
        log_message(f"✅ FFmpeg найден локально")
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

# ==================== БЫСТРОЕ СЖАТИЕ ВИДЕО ====================
def get_video_size_mb(file_path: str) -> float:
    """Быстрое получение размера видео в МБ"""
    try:
        return os.path.getsize(file_path) / (1024 * 1024)
    except:
        return 0

def compress_video_fast(input_path: str) -> str:
    """
    МГНОВЕННОЕ сжатие видео (5-15 секунд)
    Всегда сжимает до ~45 МБ
    """
    global FFMPEG_PATH
    
    if not FFMPEG_PATH:
        log_message("❌ FFmpeg не найден", "ERROR")
        return None
    
    try:
        original_size = get_video_size_mb(input_path)
        log_message(f"📊 Исходный размер: {original_size:.1f} МБ")
        
        # Если видео меньше 45 МБ - не сжимаем
        if original_size <= 45:
            log_message(f"✅ Видео уже меньше 45 МБ, сжатие не требуется")
            return input_path
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # СУПЕР БЫСТРЫЕ параметры сжатия (5-15 секунд)
        cmd = [
            FFMPEG_PATH, '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',     # Самый быстрый
            '-crf', '28',                # Постоянное качество (чем выше, тем меньше размер)
            '-c:a', 'aac',
            '-b:a', '96k',               # Низкий битрейт аудио
            '-movflags', '+faststart',
            '-threads', '0',             # Все ядра CPU
            '-y', output_path
        ]
        
        log_message(f"⚡ Запуск БЫСТРОГО сжатия...")
        
        # Запускаем сжатие
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = get_video_size_mb(output_path)
            saved = original_size - new_size
            percent = (saved / original_size) * 100
            
            log_message(f"✅ Сжато: {original_size:.1f} МБ -> {new_size:.1f} МБ (экономия {percent:.1f}%)")
            return output_path
        else:
            if result.stderr:
                log_message(f"Ошибка: {result.stderr[:200]}", "ERROR")
            return None
            
    except subprocess.TimeoutExpired:
        log_message("❌ Сжатие превысило лимит времени", "ERROR")
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
    
    log_message(f"📥 Скачивание: {url[:50]}... | {quality}")
    
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
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'merge_output_format': 'mp4',
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'socket_timeout': 30,
            'retries': 5,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            }
        }
        
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            opts['cookiefile'] = COOKIES_FILE
        
        with YoutubeDL(opts) as ydl:
            log_message("📡 Получение информации...")
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

# ==================== ОТПРАВКА С АВТОМАТИЧЕСКИМ СЖАТИЕМ ====================
async def send_video_with_compress(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " ⚡(кэш)" if from_cache else ""
    
    try:
        # Всегда показываем размер
        log_message(f"📊 Размер видео: {file_size_mb:.1f} МБ")
        
        # Если видео меньше 50 МБ - отправляем сразу
        if file_size_mb <= 50:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:70]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Отправлено без сжатия ({file_size_mb:.1f} МБ)")
            return True
        
        # Если видео больше - сжимаем
        status_msg = await message.answer(
            f"⚡ *Сжатие видео...*\n"
            f"📦 Размер: {file_size_mb:.1f} МБ\n"
            f"🎯 Цель: ~45 МБ\n"
            f"⏱️ Ожидайте 10-30 секунд",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        compressed_path = await loop.run_in_executor(None, compress_video_fast, file_path)
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= 50:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:70]}*{cache_text} ⚡\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                log_message(f"✅ Отправлено со сжатием ({new_size:.1f} МБ)")
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                # Если сжатие не помогло, отправляем оригинал
                await status_msg.edit_text(
                    f"⚠️ *Сжатие не помогло* ({new_size:.1f} МБ)\n"
                    f"Отправляю оригинальное видео",
                    parse_mode=ParseMode.MARKDOWN
                )
                video_file = FSInputFile(file_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"⚠️ *{title[:70]}*{cache_text}\n📹 {quality} | {new_size:.1f} МБ (превышает лимит Telegram)",
                    parse_mode=ParseMode.MARKDOWN
                )
                return True
        else:
            # Если сжатие не удалось, отправляем оригинал
            await status_msg.edit_text(
                f"⚠️ *Ошибка сжатия*\n"
                f"Отправляю оригинальное видео",
                parse_mode=ParseMode.MARKDOWN
            )
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"⚠️ *{title[:70]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        await message.answer(f"❌ *Ошибка:* `{str(e)[:100]}`\nПопробуйте другое качество", parse_mode=ParseMode.MARKDOWN)
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
    cookies_exists = os.path.exists(COOKIES_FILE)
    
    await message.answer(
        f"🎬 *Видео-Бот (Быстрое сжатие)*\n\n"
        f"📹 Отправьте ссылку на YouTube видео\n\n"
        f"*Статус:*\n"
        f"🎬 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {'✅ Загружены' if cookies_exists else '❌ Не загружены'}\n\n"
        f"⚡ *Особенности:*\n"
        f"• Автоматическое сжатие видео >50 МБ\n"
        f"• Сжатие за 10-30 секунд\n"
        f"• Кэширование видео\n\n"
        f"*Команды:*\n"
        f"/cookies - Загрузить cookies\n"
        f"/stats - Статистика\n"
        f"/clear - Очистить кэш",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("cookies"))
async def cookies_cmd(message: types.Message):
    await message.answer(
        "🍪 *Загрузка cookies для YouTube*\n\n"
        "*Инструкция:*\n"
        "1. Установите расширение 'Get cookies.txt LOCALLY'\n"
        "2. Войдите в YouTube в браузере\n"
        "3. Нажмите на иконку расширения\n"
        "4. Выберите 'Export cookies'\n"
        "5. Отправьте полученный файл сюда\n\n"
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
        "🎥 *Выберите качество:*\n\n"
        "💡 *Совет:* Для больших видео выбирайте 720p или 480p",
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
            f"⏳ *Скачиваю {quality_name}...*\nПожалуйста, подождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text(
                "❌ *Ошибка скачивания*\n\n"
                "1. Загрузите cookies: /cookies\n"
                "2. Попробуйте другое качество\n"
                "3. Проверьте ссылку",
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
        
        status_msg = await callback.message.edit_text(
            "⏳ *Скачиваю аудио (MP3)...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка скачивания аудио*", parse_mode=ParseMode.MARKDOWN)
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
    print("⚡ АВТОМАТИЧЕСКОЕ СЖАТИЕ ВИДЕО")
    print("=" * 60)
    
    if ensure_ffmpeg():
        print("✅ FFmpeg готов")
    else:
        print("❌ FFmpeg не установлен")
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📁 Папка сжатия: {os.path.abspath(COMPRESSED_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("⚡ Видео >50 МБ сжимаются за 10-30 секунд")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
