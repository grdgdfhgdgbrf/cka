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
import ctypes
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА
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

# Форматы качества (исправленные)
QUALITY_FORMATS = {
    "144p": "bestvideo[height<=144]+bestaudio/best[height<=144]",
    "240p": "bestvideo[height<=240]+bestaudio/best[height<=240]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "best": "bestvideo+bestaudio/best",
}

QUALITY_NAMES = {
    "144p": "144p",
    "240p": "240p",
    "360p": "360p",
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p",
    "best": "Best"
}

# ==================== УСТАНОВКА NODE.JS (JavaScript Runtime) ====================
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
        
        # Устанавливаем в тихом режиме
        log_message("📦 Устанавливаю Node.js (это может занять минуту)...")
        subprocess.run(['msiexec', '/i', installer_path, '/quiet', '/norestart'], 
                      capture_output=True, timeout=120)
        
        # Добавляем в PATH
        node_path = r"C:\Program Files\nodejs"
        if os.path.exists(node_path):
            os.environ['PATH'] = node_path + os.pathsep + os.environ['PATH']
            subprocess.run(f'setx /M PATH "{node_path};%PATH%"', shell=True, capture_output=True)
        
        # Очистка
        os.remove(installer_path)
        
        log_message("✅ Node.js установлен!")
        return check_nodejs()
        
    except Exception as e:
        log_message(f"❌ Ошибка установки Node.js: {e}", "ERROR")
        return False

def install_nodejs_alternative():
    """Альтернативная установка Node.js через winget"""
    try:
        log_message("Пробую установить Node.js через winget...")
        subprocess.run(['winget', 'install', 'OpenJS.NodeJS', '--silent'], 
                      capture_output=True, timeout=120)
        return check_nodejs()
    except:
        return False

# ==================== УСТАНОВКА И ОБНОВЛЕНИЕ YT-DLP ====================
def update_yt_dlp():
    """Обновление yt-dlp до последней версии"""
    try:
        log_message("🔄 Обновляю yt-dlp до последней версии...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        log_message("✅ yt-dlp обновлён!")
        return True
    except Exception as e:
        log_message(f"❌ Ошибка обновления yt-dlp: {e}", "ERROR")
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
        log_message("✅ FFmpeg найден в C:\\ffmpeg")
        return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    """Установка FFmpeg на Windows"""
    try:
        log_message("🚀 Устанавливаю FFmpeg...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg.zip")
        extract_path = os.path.join(os.getcwd(), "ffmpeg_extract")
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим bin папку
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        target_path = r"C:\ffmpeg"
        target_bin = os.path.join(target_path, "bin")
        
        if os.path.exists(target_path):
            shutil.rmtree(target_path, ignore_errors=True)
        
        os.makedirs(target_bin, exist_ok=True)
        
        for file in os.listdir(bin_path):
            shutil.copy2(os.path.join(bin_path, file), os.path.join(target_bin, file))
        
        # Добавляем в PATH
        os.environ['PATH'] = target_bin + os.pathsep + os.environ['PATH']
        subprocess.run(f'setx /M PATH "{target_bin};%PATH%"', shell=True, capture_output=True)
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        log_message("✅ FFmpeg установлен!")
        return check_ffmpeg()
        
    except Exception as e:
        log_message(f"❌ Ошибка установки FFmpeg: {e}", "ERROR")
        return False

# ==================== ФУНКЦИЯ СКАЧИВАНИЯ ВИДЕО (ИСПРАВЛЕННАЯ) ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    unique_string = f"{url}_{quality}_{file_type}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def download_video_sync(url: str, quality: str):
    """Скачивание видео с исправленными форматами"""
    video_id = get_video_id(url, quality, "video")
    log_message(f"Скачивание видео: {url[:100]}, качество: {quality}")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Видео из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        format_str = QUALITY_FORMATS.get(quality, "bestvideo+bestaudio/best")
        
        # ИСПРАВЛЕННЫЕ НАСТРОЙКИ для YouTube
        opts = {
            'format': format_str,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',
            'ignoreerrors': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls', 'live'],  # Пропускаем проблемные форматы
                    'player_client': ['android', 'web'],  # Используем android клиент
                }
            },
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }
        
        # Используем yt-dlp с обновлёнными настройками
        from yt_dlp import YoutubeDL
        
        with YoutubeDL(opts) as ydl:
            log_message("Получаю информацию о видео...")
            
            # Сначала получаем список доступных форматов
            info = ydl.extract_info(url, download=False)
            if not info:
                log_message("❌ Не удалось получить информацию", "ERROR")
                return None, None, False
            
            # Логируем доступные форматы
            if 'formats' in info:
                available_heights = sorted(set(f.get('height', 0) for f in info['formats'] if f.get('height')))
                log_message(f"Доступные качества: {available_heights}")
            
            # Скачиваем
            info = ydl.extract_info(url, download=True)
            
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
        from yt_dlp import YoutubeDL
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
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

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА ВСЕГО ====================
def auto_setup():
    """Автоматическая установка всего необходимого"""
    log_message("=" * 50)
    log_message("🔧 ПРОВЕРКА И УСТАНОВКА КОМПОНЕНТОВ")
    log_message("=" * 50)
    
    # 1. Обновляем yt-dlp
    log_message("1️⃣ Проверяю yt-dlp...")
    update_yt_dlp()
    
    # 2. Устанавливаем Node.js (нужен для YouTube)
    log_message("2️⃣ Проверяю Node.js...")
    if not check_nodejs():
        log_message("Устанавливаю Node.js...")
        if not install_nodejs_windows():
            install_nodejs_alternative()
    
    # 3. Устанавливаем FFmpeg
    log_message("3️⃣ Проверяю FFmpeg...")
    if not check_ffmpeg():
        log_message("Устанавливаю FFmpeg...")
        install_ffmpeg_windows()
    
    log_message("=" * 50)
    log_message("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    log_message("=" * 50)

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
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n⚠️ Видео >50 МБ, отправлено как файл",
                parse_mode=ParseMode.MARKDOWN
            )
        log_message(f"✅ Файл отправлен")
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
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте ссылку на видео с YouTube, Instagram, TikTok и других сайтов.\n\n"
        "🔧 /setup — Установить всё необходимое\n"
        "📊 /stats — Статистика\n"
        "🗑️ /clear_cache — Очистить кэш",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("setup"))
async def setup_command(message: types.Message):
    await message.answer("🔧 Начинаю установку компонентов...\nЭто может занять 1-2 минуты.")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, auto_setup)
    await message.answer("✅ Установка завершена! Теперь бот готов к работе.")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    node_ok = check_nodejs()
    ffmpeg_ok = check_ffmpeg()
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🟢 Node.js: {'✅' if node_ok else '❌'}\n"
        f"🎬 FFmpeg: {'✅' if ffmpeg_ok else '❌'}\n\n"
        f"Если что-то не работает, отправьте /setup",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
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
    await message.answer(f"🗑️ Очищено {deleted} файлов")

# ==================== ОБРАБОТЧИКИ ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
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
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality_name}*...", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания.\nПопробуйте /setup для установки компонентов.")
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
    
    # Автоматическая установка всего при первом запуске
    auto_setup()
    
    print("✅ Бот готов к работе!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
