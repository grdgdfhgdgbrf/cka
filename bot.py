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
CACHE_DIR = "cache"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

for dir_name in [DOWNLOAD_DIR, CACHE_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

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
log_message(f"Загружено {len(video_cache)} записей кэша")

# ==================== ОБНОВЛЕНИЕ YT-DLP ====================
def update_yt_dlp():
    """Обновление yt-dlp до последней версии"""
    try:
        log_message("🔄 Проверяю обновления yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        log_message("✅ yt-dlp обновлён до последней версии")
        return True
    except Exception as e:
        log_message(f"❌ Ошибка обновления yt-dlp: {e}", "ERROR")
        return False

# ==================== УСТАНОВКА NODE.JS (JavaScript Runtime) ====================
def install_nodejs_windows():
    """Установка Node.js для JavaScript runtime"""
    try:
        log_message("🚀 Устанавливаю Node.js (нужен для YouTube)...")
        
        # Скачиваем Node.js installer
        node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
        installer_path = os.path.join(os.getcwd(), "node_installer.msi")
        
        log_message(f"📥 Скачиваю Node.js...")
        urllib.request.urlretrieve(node_url, installer_path)
        
        # Устанавливаем тихо
        log_message("📦 Устанавливаю Node.js...")
        subprocess.run(f'msiexec /i "{installer_path}" /quiet /norestart', shell=True, timeout=120)
        
        # Добавляем в PATH
        node_path = r"C:\Program Files\nodejs"
        if os.path.exists(node_path):
            os.environ['PATH'] = node_path + os.pathsep + os.environ['PATH']
        
        # Очистка
        if os.path.exists(installer_path):
            os.remove(installer_path)
        
        log_message("✅ Node.js установлен!")
        return True
    except Exception as e:
        log_message(f"❌ Ошибка установки Node.js: {e}", "ERROR")
        return False

def check_nodejs() -> bool:
    """Проверка наличия Node.js"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            log_message(f"✅ Node.js найден: {result.stdout.strip()}")
            return True
    except:
        pass
    log_message("❌ Node.js не найден", "WARNING")
    return False

# ==================== УСТАНОВКА FFMPEG ====================
def add_to_system_path(path_to_add: str):
    try:
        subprocess.run(f'setx /M PATH "{path_to_add};%PATH%"', shell=True, capture_output=True)
        os.environ['PATH'] = path_to_add + os.pathsep + os.environ['PATH']
        log_message(f"✅ PATH обновлён: {path_to_add}")
        return True
    except Exception as e:
        log_message(f"Ошибка обновления PATH: {e}", "ERROR")
        return False

def check_ffmpeg() -> bool:
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message("✅ FFmpeg работает")
            return True
    except:
        pass
    
    # Проверяем в C:\ffmpeg\bin
    if os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe"):
        os.environ['PATH'] = r"C:\ffmpeg\bin" + os.pathsep + os.environ['PATH']
        log_message("✅ FFmpeg найден в C:\\ffmpeg\\bin")
        return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    try:
        log_message("🚀 Устанавливаю FFmpeg...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg_temp.zip")
        extract_path = os.path.join(os.getcwd(), "ffmpeg_extract_temp")
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
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
                shutil.copy2(os.path.join(bin_path, file), os.path.join(target_bin, file))
            
            add_to_system_path(target_bin)
        
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        return check_ffmpeg()
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def auto_install_ffmpeg():
    if check_ffmpeg():
        return True
    log_message("⚠️ FFmpeg не найден, устанавливаю...")
    return install_ffmpeg_windows()

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ВИДЕО ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    return hashlib.md5(f"{url}_{quality}_{file_type}".encode()).hexdigest()

def get_available_formats(url: str):
    """Получение списка доступных форматов видео"""
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            # Собираем доступные качества
            available = []
            for f in formats:
                height = f.get('height')
                if height and height <= 1080 and f.get('vcodec') != 'none':
                    if height not in available:
                        available.append(height)
            
            return sorted(available, reverse=True)
    except Exception as e:
        log_message(f"Ошибка получения форматов: {e}", "ERROR")
        return []

def download_video_sync(url: str, quality: str):
    """Скачивание видео с исправленными настройками для YouTube"""
    video_id = get_video_id(url, quality, "video")
    log_message(f"Скачивание видео: {url[:100]}, качество: {quality}")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Видео из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        # ИСПРАВЛЕННЫЕ НАСТРОЙКИ для YouTube
        if quality == "best":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif quality == "480p":
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]"
        elif quality == "360p":
            format_str = "bestvideo[height<=360]+bestaudio/best[height<=360]"
        elif quality == "240p":
            format_str = "worstvideo[height<=240]+bestaudio/worst[height<=240]"
        elif quality == "144p":
            format_str = "worstvideo[height<=144]+bestaudio/worst[height<=144]"
        else:
            format_str = "best[height<=720]"
        
        opts = {
            'format': format_str,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',
            'ignoreerrors': True,
            'extract_flat': False,
            # Добавляем User-Agent для обхода блокировок
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
        
        # Пробуем альтернативный формат если первый не работает
        try:
            with YoutubeDL(opts) as ydl:
                log_message("Получаю информацию о видео...")
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            log_message(f"Ошибка с форматом {format_str}, пробую best...", "WARNING")
            opts['format'] = 'best'
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        
        if not info:
            log_message("❌ Не удалось получить информацию", "ERROR")
            return None, None, False
        
        title = info.get('title', 'video')
        title = "".join(c for c in title if c not in r'\/:*?"<>|')
        filename = ydl.prepare_filename(info)
        
        # Ищем файл
        if not os.path.exists(filename):
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            else:
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and f.endswith('.mp4')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    log_message("❌ Файл не найден", "ERROR")
                    return None, None, False
        
        file_size = os.path.getsize(filename) / (1024 * 1024)
        log_message(f"✅ Видео скачано: {title}, {file_size:.1f} МБ")
        
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
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио"""
    audio_id = get_video_id(url, "mp3", "audio")
    log_message(f"Скачивание аудио: {url[:100]}")
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Аудио из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp3') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            else:
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and f.endswith('.mp3')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Аудио скачано: {title}, {file_size:.1f} МБ")
            
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
        log_message(f"❌ Ошибка: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА ФАЙЛОВ ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " (из кэша ⚡)" if from_cache else ""
    
    try:
        if file_size_mb <= 50:
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
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
        log_message(f"✅ Файл отправлен: {file_size_mb:.1f} МБ")
    except Exception as e:
        log_message(f"❌ Ошибка отправки: {e}", "ERROR")
        raise

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== КЛАВИАТУРА ====================
def get_quality_keyboard(url: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Best", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    return keyboard

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    log_message(f"Пользователь {message.from_user.id}: /start")
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте ссылку на видео.\n\n"
        "🔧 /check — Проверить FFmpeg\n"
        "🗑️ /clear_cache — Очистить кэш\n"
        "📊 /stats — Статистика\n"
        "📋 /log — Логи\n"
        "🔄 /update — Обновить yt-dlp",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("update"))
async def update_command(message: types.Message):
    await message.answer("🔄 Обновляю yt-dlp...")
    if update_yt_dlp():
        await message.answer("✅ yt-dlp обновлён! Перезапустите бота.")
    else:
        await message.answer("❌ Ошибка обновления")

@dp.message(Command("check"))
async def check_command(message: types.Message):
    await message.answer("🔍 Проверяю компоненты...")
    msg = "📊 *Результат проверки:*\n\n"
    
    # Проверка FFmpeg
    if check_ffmpeg():
        msg += "✅ FFmpeg: установлен\n"
    else:
        msg += "❌ FFmpeg: не установлен\n"
        auto_install_ffmpeg()
    
    # Проверка Node.js
    if check_nodejs():
        msg += "✅ Node.js: установлен\n"
    else:
        msg += "⚠️ Node.js: не установлен (нужен для YouTube)\n"
    
    await message.answer(msg, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("log"))
async def log_command(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:]
            await message.answer(f"📋 *Логи:*\n```\n{''.join(last_lines)[:3000]}\n```", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
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
async def stats_command(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info['path']):
            total_size += os.path.getsize(info['path'])
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"⚡ FFmpeg: {'✅' if check_ffmpeg() else '❌'}\n"
        f"🟢 Node.js: {'✅' if check_nodejs() else '❌'}",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИКИ ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку (http:// или https://)")
        return
    
    await message.answer("🎥 *Выберите качество:*", reply_markup=get_quality_keyboard(url), parse_mode=ParseMode.MARKDOWN)

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
        quality_name = QUALITY_NAMES.get(quality, quality)
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality_name}*...\nЭто может занять 1-2 минуты", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания.\nПопробуйте другое качество или /log")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality_name, from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания аудио")
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*\n🎵 MP3 | {file_size:.1f} МБ" + (" ⚡(кэш)" if from_cache else ""),
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Обновляем yt-dlp
    update_yt_dlp()
    
    # Устанавливаем FFmpeg если нужно
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, устанавливаю...")
        auto_install_ffmpeg()
    else:
        print("✅ FFmpeg уже установлен")
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📄 Логи: {LOG_FILE}")
    print("=" * 60)
    print("✅ Бот готов!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
