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

DOWNLOAD_DIR = "downloads"
COMPRESSED_DIR = "compressed"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR]:
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

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА FFMPEG ====================
def download_file(url, filename):
    """Скачивание файла с прогрессом"""
    urllib.request.urlretrieve(url, filename)
    return filename

def add_to_path(path_to_add):
    """Добавление пути в системную переменную PATH"""
    try:
        current_path = os.environ.get('PATH', '')
        if path_to_add not in current_path:
            os.environ['PATH'] = path_to_add + os.pathsep + current_path
            
            # Для постоянного сохранения
            if platform.system() == "Windows":
                subprocess.run(f'setx PATH "{path_to_add};%PATH%"', shell=True, capture_output=True)
            return True
    except Exception as e:
        log_message(f"Ошибка добавления в PATH: {e}", "WARNING")
    return False

def install_ffmpeg_auto():
    """Полностью автоматическая установка FFmpeg"""
    try:
        log_message("🚀 Автоматическая установка FFmpeg...")
        
        # Создаем папку для FFmpeg
        ffmpeg_dir = os.path.join(os.getcwd(), "ffmpeg_bin")
        if not os.path.exists(ffmpeg_dir):
            os.makedirs(ffmpeg_dir)
        
        # Скачиваем FFmpeg
        if platform.system() == "Windows":
            ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = os.path.join(ffmpeg_dir, "ffmpeg.zip")
        else:
            ffmpeg_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            zip_path = os.path.join(ffmpeg_dir, "ffmpeg.tar.xz")
        
        log_message(f"📥 Скачивание FFmpeg...")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        # Распаковка
        if platform.system() == "Windows":
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(ffmpeg_dir)
            
            # Поиск ffmpeg.exe
            for root, dirs, files in os.walk(ffmpeg_dir):
                if 'ffmpeg.exe' in files:
                    bin_path = root
                    break
        else:
            import tarfile
            with tarfile.open(zip_path, 'r:xz') as tar_ref:
                tar_ref.extractall(ffmpeg_dir)
            
            for root, dirs, files in os.walk(ffmpeg_dir):
                if 'ffmpeg' in files and 'bin' in root:
                    bin_path = root
                    break
        
        # Добавляем в PATH
        add_to_path(bin_path)
        
        # Очистка
        os.remove(zip_path)
        
        log_message(f"✅ FFmpeg установлен в: {bin_path}")
        return True
        
    except Exception as e:
        log_message(f"❌ Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg"""
    try:
        # Проверяем в текущей сессии
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message("✅ FFmpeg найден")
            return True
    except:
        pass
    
    # Проверяем в локальной папке
    ffmpeg_paths = [
        os.path.join(os.getcwd(), "ffmpeg_bin", "ffmpeg.exe"),
        os.path.join(os.getcwd(), "ffmpeg_bin", "bin", "ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"
    ]
    
    for path in ffmpeg_paths:
        if os.path.exists(path):
            bin_dir = os.path.dirname(path)
            add_to_path(bin_dir)
            log_message(f"✅ FFmpeg найден: {path}")
            return True
    
    log_message("❌ FFmpeg не найден")
    return False

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА NODE.JS ====================
def install_nodejs_auto():
    """Автоматическая установка Node.js для YouTube"""
    try:
        log_message("🚀 Автоматическая установка Node.js...")
        
        node_dir = os.path.join(os.getcwd(), "nodejs_bin")
        if not os.path.exists(node_dir):
            os.makedirs(node_dir)
        
        if platform.system() == "Windows":
            # Скачиваем Node.js portable
            node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip"
            zip_path = os.path.join(node_dir, "node.zip")
        else:
            node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.xz"
            zip_path = os.path.join(node_dir, "node.tar.xz")
        
        log_message(f"📥 Скачивание Node.js...")
        urllib.request.urlretrieve(node_url, zip_path)
        
        # Распаковка
        if platform.system() == "Windows":
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(node_dir)
            
            # Поиск node.exe
            for root, dirs, files in os.walk(node_dir):
                if 'node.exe' in files:
                    bin_path = root
                    break
        else:
            import tarfile
            with tarfile.open(zip_path, 'r:xz') as tar_ref:
                tar_ref.extractall(node_dir)
            
            for root, dirs, files in os.walk(node_dir):
                if 'node' in files and 'bin' in root:
                    bin_path = root
                    break
        
        # Добавляем в PATH
        add_to_path(bin_path)
        
        # Очистка
        os.remove(zip_path)
        
        log_message(f"✅ Node.js установлен в: {bin_path}")
        return True
        
    except Exception as e:
        log_message(f"⚠️ Node.js не установлен (не критично): {e}", "WARNING")
        return False

def check_nodejs() -> bool:
    """Проверка Node.js"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message(f"✅ Node.js: {result.stdout.strip()}")
            return True
    except:
        pass
    
    # Проверка в локальной папке
    node_paths = [
        os.path.join(os.getcwd(), "nodejs_bin", "node.exe"),
        os.path.join(os.getcwd(), "nodejs_bin", "bin", "node.exe"),
        r"C:\Program Files\nodejs\node.exe"
    ]
    
    for path in node_paths:
        if os.path.exists(path):
            bin_dir = os.path.dirname(path)
            add_to_path(bin_dir)
            log_message(f"✅ Node.js найден: {path}")
            return True
    
    return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    """Сжатие видео до указанного размера"""
    try:
        if not check_ffmpeg():
            log_message("❌ FFmpeg не найден", "ERROR")
            return None
        
        # Получаем длительность
        probe_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip()) if result.stdout else 60
        
        # Рассчёт битрейта
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(500000, min(video_bitrate, 3000000))
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Сжатие
        compress_cmd = [
            'ffmpeg', '-i', input_path,
            '-b:v', f'{video_bitrate}',
            '-b:a', '128k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"Сжатие: битрейт {video_bitrate} bps")
        
        result = subprocess.run(compress_cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {new_size:.1f} МБ")
            return output_path
        else:
            return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео"""
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {quality}")
    
    try:
        quality_map = {
            "144p": 'worst[height<=144]',
            "240p": 'best[height<=240]',
            "360p": 'best[height<=360]',
            "480p": 'best[height<=480]',
            "720p": 'best[height<=720]',
            "1080p": 'best[height<=1080]',
            "best": 'best'
        }
        format_spec = quality_map.get(quality, 'best[height<=720]')
        
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'merge_output_format': 'mp4',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
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
        log_message(f"Ошибка: {e}", "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио"""
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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
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

# ==================== ОТПРАВКА С СЖАТИЕМ ====================
async def send_video_with_compress(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    """Отправка видео с автоматическим сжатием"""
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
        
        # Сжатие
        log_message(f"Сжатие {file_size_mb:.1f} МБ -> 48 МБ")
        status_msg = await message.answer(f"📦 *Видео {file_size_mb:.1f} МБ > 50 МБ*\n⏳ Сжимаю...\n_Это может занять 2-5 минут_", parse_mode=ParseMode.MARKDOWN)
        
        compressed_path = await asyncio.get_event_loop().run_in_executor(
            None, compress_video, file_path, 48
        )
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= LIMIT:
                await status_msg.delete()
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:80]}*{cache_text} 🗜️(сжато)\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                log_message(f"✅ Отправлено со сжатием ({new_size:.1f} МБ)")
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(f"❌ *Не удалось сжать*\nПопробуйте качество ниже (480p или 360p)", parse_mode=ParseMode.MARKDOWN)
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

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте ссылку на видео\n\n"
        "*Возможности:*\n"
        "• Автоматическое сжатие видео >50 МБ\n"
        "• Кэширование\n"
        "• MP3 аудио\n\n"
        "*Команды:*\n"
        "/stats - Статистика\n"
        "/clear - Очистить кэш",
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
        f"📁 В кэше: {len(video_cache)}\n"
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

# ==================== ОБРАБОТКА ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(
        "🎥 *Выберите качество:*",
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
        
        status_msg = await callback.message.edit_text(f"⏳ *Скачиваю {quality_name}...*\nПодождите", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка*\nПопробуйте другое качество", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            return
        
        await status_msg.edit_text(f"📤 *Обработка...*", parse_mode=ParseMode.MARKDOWN)
        
        success = await send_video_with_compress(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        status_msg = await callback.message.edit_text("⏳ *Скачиваю MP3...*", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await status_msg.edit_text("❌ *Ошибка*", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " ⚡(кэш)" if from_cache else ""
        
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

# ==================== ЗАПУСК С АВТОУСТАНОВКОЙ ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    
    # Автоматическая установка FFmpeg
    print("🔧 Проверка FFmpeg...")
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, автоматическая установка...")
        install_ffmpeg_auto()
        time.sleep(2)
        check_ffmpeg()
    else:
        print("✅ FFmpeg готов")
    
    # Автоматическая установка Node.js
    print("🔧 Проверка Node.js...")
    if not check_nodejs():
        print("⚠️ Node.js не найден, автоматическая установка...")
        install_nodejs_auto()
        time.sleep(2)
        check_nodejs()
    else:
        print("✅ Node.js готов")
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
