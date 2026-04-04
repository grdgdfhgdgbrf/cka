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

# ==================== УСТАНОВКА FFMPEG ====================
def check_ffmpeg() -> bool:
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
        log_message("✅ FFmpeg найден в C:\\ffmpeg\\bin")
        return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    try:
        log_message("🚀 Установка FFmpeg...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = "ffmpeg.zip"
        extract_path = "ffmpeg_temp"
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим bin папку
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        target_path = r"C:\ffmpeg"
        if os.path.exists(target_path):
            shutil.rmtree(target_path, ignore_errors=True)
        
        shutil.copytree(bin_path, os.path.join(target_path, "bin"))
        
        # Добавляем в PATH
        subprocess.run(f'setx /M PATH "%PATH%;C:\\ffmpeg\\bin"', shell=True, capture_output=True)
        os.environ['PATH'] = r"C:\ffmpeg\bin" + os.pathsep + os.environ['PATH']
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        log_message("✅ FFmpeg установлен")
        return True
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

# ==================== УСТАНОВКА NODE.JS ДЛЯ YT-DLP ====================
def check_nodejs() -> bool:
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message(f"✅ Node.js найден: {result.stdout.strip()}")
            return True
    except:
        pass
    log_message("❌ Node.js не найден", "WARNING")
    return False

def install_nodejs_windows():
    try:
        log_message("🚀 Установка Node.js (нужен для YouTube)...")
        
        node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
        msi_path = "nodejs.msi"
        
        urllib.request.urlretrieve(node_url, msi_path)
        
        # Тихая установка
        subprocess.run(f'msiexec /i "{msi_path}" /quiet /norestart', shell=True, timeout=120)
        
        # Добавляем в PATH
        node_paths = [
            r"C:\Program Files\nodejs",
            r"C:\Program Files (x86)\nodejs"
        ]
        for path in node_paths:
            if os.path.exists(path):
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                subprocess.run(f'setx /M PATH "%PATH%;{path}"', shell=True, capture_output=True)
                break
        
        os.remove(msi_path)
        log_message("✅ Node.js установлен")
        return True
    except Exception as e:
        log_message(f"Ошибка установки Node.js: {e}", "ERROR")
        return False

def update_yt_dlp():
    """Обновление yt-dlp до последней версии"""
    try:
        log_message("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        log_message("✅ yt-dlp обновлён")
        return True
    except Exception as e:
        log_message(f"Ошибка обновления yt-dlp: {e}", "ERROR")
        return False

# ==================== ФУНКЦИИ СКАЧИВАНИЯ ====================
def get_video_id(url: str, quality: str) -> str:
    return hashlib.md5(f"{url}_{quality}".encode()).hexdigest()

def get_available_formats(url: str):
    """Получение доступных форматов видео"""
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            available = []
            for f in formats:
                height = f.get('height', 0)
                if height and height <= 1080:
                    available.append(height)
            
            available = sorted(set(available))
            log_message(f"Доступные качества: {available}")
            return available
    except Exception as e:
        log_message(f"Ошибка получения форматов: {e}", "WARNING")
        return [360, 480, 720]

def download_video_sync(url: str, quality: str):
    """Скачивание видео с правильными форматами"""
    video_id = get_video_id(url, quality)
    
    # Проверка кэша
    if video_id in video_cache and os.path.exists(video_cache[video_id]['path']):
        log_message(f"✅ Видео из кэша")
        cached = video_cache[video_id]
        return cached['path'], cached['title'], True
    
    try:
        # Преобразуем качество в число
        quality_map = {
            "144p": 144, "240p": 240, "360p": 360,
            "480p": 480, "720p": 720, "1080p": 1080,
            "best": 2160
        }
        target_height = quality_map.get(quality, 720)
        
        # Правильный формат для YouTube
        if target_height <= 720:
            format_spec = f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={target_height}][ext=mp4]/best'
        else:
            format_spec = f'bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]/best'
        
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s_%(height)sp.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
            'extract_flat': False,
            # Добавляем User-Agent чтобы не блокировали
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        log_message(f"Скачивание {quality} (высота: {target_height})")
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Находим файл
            filename = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if f.endswith('.mp4')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title} ({file_size:.1f} МБ)")
            
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
    audio_id = hashlib.md5(f"{url}_audio".encode()).hexdigest()
    
    if audio_id in video_cache and os.path.exists(video_cache[audio_id]['path']):
        cached = video_cache[audio_id]
        return cached['path'], cached['title'], True
    
    try:
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
                        if f.endswith('.mp3')]
                if files:
                    filename = max(files, key=os.path.getmtime)
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
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " ⚡(кэш)" if from_cache else ""
    
    try:
        if file_size_mb <= 50:
            video_file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            doc_file = FSInputFile(file_path)
            await bot.send_document(
                chat_id=chat_id,
                document=doc_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n⚠️ >50 МБ",
                parse_mode=ParseMode.MARKDOWN
            )
        log_message(f"✅ Отправлено: {file_size_mb:.1f} МБ")
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
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
        "🔧 /check — Проверить установку\n"
        "📊 /stats — Статистика\n"
        "🗑️ /clear — Очистить кэш",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    status = "🔍 *Проверка системы:*\n\n"
    status += f"✅ FFmpeg: {'✅' if check_ffmpeg() else '❌'}\n"
    status += f"✅ Node.js: {'✅' if check_nodejs() else '❌'}\n"
    status += f"✅ yt-dlp: {'✅' if update_yt_dlp() else '⚠️'}\n"
    await message.answer(status, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = sum(info.get('size_mb', 0) for info in video_cache.values())
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size:.1f} МБ",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear"))
async def clear_cmd(message: types.Message):
    global video_cache
    for info in video_cache.values():
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
            except:
                pass
    video_cache = {}
    save_cache(video_cache)
    await message.answer("🗑️ Кэш очищен")

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку")
        return
    
    await message.answer("🎥 *Выберите качество:*", reply_markup=get_keyboard(url), parse_mode=ParseMode.MARKDOWN)

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
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality}*...\nYouTube может обрабатывать 1-2 минуты", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка. Попробуйте другое качество или проверьте ссылку")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality, from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка")
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:80]}*\n🎵 MP3 | {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 50)
    
    # Установка всего необходимого
    if not check_ffmpeg():
        install_ffmpeg_windows()
    
    if not check_nodejs():
        install_nodejs_windows()
    
    update_yt_dlp()
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
