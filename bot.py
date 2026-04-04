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
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

DOWNLOAD_DIR = "downloads"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

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

# Загрузка кэша
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_message(f"Ошибка загрузки кэша: {e}", "ERROR")
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_message(f"Ошибка сохранения кэша: {e}", "ERROR")

video_cache = load_cache()

# ==================== УСТАНОВКА NODE.JS (JavaScript runtime для YouTube) ====================
def check_nodejs() -> bool:
    """Проверка наличия Node.js"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message(f"✅ Node.js найден: {result.stdout.strip()}")
            return True
    except:
        pass
    log_message("❌ Node.js не найден")
    return False

def install_nodejs_windows():
    """Установка Node.js на Windows"""
    try:
        log_message("🚀 Устанавливаю Node.js...")
        
        # Скачиваем Node.js installer
        node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
        installer_path = os.path.join(os.getcwd(), "node_installer.msi")
        
        log_message(f"📥 Скачиваю Node.js с {node_url}")
        urllib.request.urlretrieve(node_url, installer_path)
        
        # Устанавливаем тихо
        log_message("📦 Устанавливаю Node.js (это может занять минуту)...")
        subprocess.run(['msiexec', '/i', installer_path, '/quiet', '/norestart'], 
                      capture_output=True, timeout=120)
        
        # Добавляем в PATH
        node_path = r"C:\Program Files\nodejs"
        os.environ['PATH'] = node_path + os.pathsep + os.environ['PATH']
        
        # Очистка
        if os.path.exists(installer_path):
            os.remove(installer_path)
        
        log_message("✅ Node.js установлен!")
        return check_nodejs()
        
    except Exception as e:
        log_message(f"❌ Ошибка установки Node.js: {e}", "ERROR")
        return False

# ==================== УСТАНОВКА FFMPEG ====================
def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message("✅ FFmpeg найден")
            return True
    except:
        pass
    
    # Проверяем в C:\ffmpeg
    if os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe"):
        os.environ['PATH'] = r"C:\ffmpeg\bin" + os.pathsep + os.environ['PATH']
        log_message("✅ FFmpeg найден в C:\ffmpeg")
        return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    """Установка FFmpeg на Windows"""
    try:
        log_message("🚀 Устанавливаю FFmpeg...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg.zip")
        extract_path = os.path.join(os.getcwd(), "ffmpeg_temp")
        
        log_message(f"📥 Скачиваю FFmpeg...")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        log_message("📦 Распаковываю...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим bin папку
        bin_path = None
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        if bin_path:
            target_path = r"C:\ffmpeg"
            target_bin = os.path.join(target_path, "bin")
            
            if os.path.exists(target_path):
                shutil.rmtree(target_path, ignore_errors=True)
            
            os.makedirs(target_bin, exist_ok=True)
            
            for file in os.listdir(bin_path):
                src = os.path.join(bin_path, file)
                dst = os.path.join(target_bin, file)
                shutil.copy2(src, dst)
            
            os.environ['PATH'] = target_bin + os.pathsep + os.environ['PATH']
            log_message("✅ FFmpeg установлен!")
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        return check_ffmpeg()
        
    except Exception as e:
        log_message(f"❌ Ошибка установки FFmpeg: {e}", "ERROR")
        return False

# ==================== НАСТРОЙКИ YT-DLP ДЛЯ YOUTUBE ====================
def get_ydl_opts(quality: str):
    """Оптимальные настройки для yt-dlp с поддержкой YouTube"""
    
    # Базовые настройки
    opts = {
        'quiet': False,
        'no_warnings': False,
        'verbose': False,
        'merge_output_format': 'mp4',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
        'ignoreerrors': True,
        'no_color': True,
        'extract_flat': False,
    }
    
    # Настройки формата для YouTube
    if quality == "audio":
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Карта качества для YouTube
        quality_map = {
            "144p": "worst[height<=144]",
            "240p": "best[height<=240]",
            "360p": "best[height<=360]",
            "480p": "best[height<=480]",
            "720p": "best[height<=720]",
            "1080p": "best[height<=1080]",
            "best": "bestvideo+bestaudio/best",
        }
        opts['format'] = quality_map.get(quality, "best[height<=720]")
    
    return opts

# ==================== ФУНКЦИИ СКАЧИВАНИЯ ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    return hashlib.md5(f"{url}_{quality}_{file_type}".encode()).hexdigest()

def download_with_ytdlp(url: str, quality: str):
    """Скачивание видео/аудио через yt-dlp"""
    is_audio = (quality == "audio")
    file_type = "audio" if is_audio else "video"
    item_id = get_video_id(url, quality, file_type)
    
    # Проверка кэша
    if item_id in video_cache:
        cached = video_cache[item_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        opts = get_ydl_opts(quality)
        log_message(f"Начинаю скачивание: {url[:80]}")
        
        with YoutubeDL(opts) as ydl:
            # Скачиваем
            info = ydl.extract_info(url, download=True)
            
            if not info:
                log_message("❌ Не удалось получить информацию", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Ищем файл
            filename = None
            ext = "mp3" if is_audio else "mp4"
            
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith(f'.{ext}') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if f.endswith(f'.{ext}')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    log_message("❌ Файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title}, {file_size:.1f} МБ")
            
            # Сохраняем в кэш
            video_cache[item_id] = {
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
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

# ==================== АВТОУСТАНОВКА ВСЕГО НЕОБХОДИМОГО ====================
def auto_install_all():
    """Автоматическая установка FFmpeg и Node.js"""
    log_message("=" * 50)
    log_message("Проверка и установка необходимых компонентов...")
    
    # Установка FFmpeg
    if not check_ffmpeg():
        log_message("Устанавливаю FFmpeg...")
        if install_ffmpeg_windows():
            log_message("✅ FFmpeg установлен")
        else:
            log_message("⚠️ Не удалось установить FFmpeg", "WARNING")
    else:
        log_message("✅ FFmpeg уже установлен")
    
    # Установка Node.js (нужен для YouTube)
    if not check_nodejs():
        log_message("Устанавливаю Node.js...")
        if install_nodejs_windows():
            log_message("✅ Node.js установлен")
        else:
            log_message("⚠️ Не удалось установить Node.js", "WARNING")
    else:
        log_message("✅ Node.js уже установлен")
    
    log_message("=" * 50)
    return check_ffmpeg() and check_nodejs()

# ==================== ОТПРАВКА ФАЙЛОВ ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " ⚡(из кэша)" if from_cache else ""
    
    try:
        if quality == "audio":
            audio_file = FSInputFile(file_path)
            await bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n🎵 MP3 | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
        elif file_size_mb <= 50:
            video_file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            document_file = FSInputFile(file_path)
            await bot.send_document(
                chat_id=chat_id,
                document=document_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n⚠️ Видео >50 МБ",
                parse_mode=ParseMode.MARKDOWN
            )
        log_message(f"✅ Отправлено: {file_size_mb:.1f} МБ")
    except Exception as e:
        log_message(f"❌ Ошибка отправки: {e}", "ERROR")
        raise

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="144p", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="720p", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Best", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте ссылку на видео с YouTube, Instagram, TikTok и др.\n\n"
        "🔧 /check - Проверить компоненты\n"
        "🗑️ /clear_cache - Очистить кэш\n"
        "📊 /stats - Статистика",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    ffmpeg_ok = check_ffmpeg()
    node_ok = check_nodejs()
    await message.answer(
        f"🔍 *Проверка:*\n\n"
        f"FFmpeg: {'✅' if ffmpeg_ok else '❌'}\n"
        f"Node.js: {'✅' if node_ok else '❌'}\n\n"
        f"Если что-то отсутствует, бот установит автоматически.",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear_cache"))
async def clear_cache_cmd(message: types.Message):
    global video_cache
    deleted = 0
    for info in video_cache.values():
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
                deleted += 1
            except:
                pass
    video_cache = {}
    save_cache(video_cache)
    await message.answer(f"🗑️ Очищено {deleted} файлов")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size:.1f} МБ",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку (http:// или https://)")
        return
    
    await message.answer("🎥 *Выберите опцию:*", reply_markup=get_keyboard(url), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    if data == "cancel":
        await callback.message.edit_text("❌ Отменено")
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
        await callback.message.edit_text(f"⏳ Скачиваю *{quality}*...\nЭто может занять минуту", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_with_ytdlp, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания.\nПроверьте ссылку и попробуйте снова.")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality, from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_with_ytdlp, url, "audio")
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания аудио")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, "audio", from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Автоустановка всего необходимого
    auto_install_all()
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📄 Логи: {LOG_FILE}")
    print("=" * 60)
    print("✅ Бот готов!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
