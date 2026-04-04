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

for dir_name in [DOWNLOAD_DIR, COMPRESSED_DIR, TOOLS_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# Добавляем tools в PATH
FFMPEG_PATH = os.path.join(os.getcwd(), TOOLS_DIR, "ffmpeg", "bin")
NODE_PATH = os.path.join(os.getcwd(), TOOLS_DIR, "nodejs")

if os.path.exists(FFMPEG_PATH):
    os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ.get('PATH', '')
if os.path.exists(NODE_PATH):
    os.environ['PATH'] = NODE_PATH + os.pathsep + os.environ.get('PATH', '')

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

# ==================== УСТАНОВКА FFMPEG ДЛЯ WINDOWS ====================
def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg"""
    try:
        # Проверяем в tools папке
        if platform.system() == "Windows":
            ffmpeg_exe = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
        else:
            ffmpeg_exe = os.path.join(FFMPEG_PATH, "ffmpeg")
        
        if os.path.exists(ffmpeg_exe):
            log_message(f"✅ FFmpeg найден: {ffmpeg_exe}")
            return True
        
        # Проверяем в PATH
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            log_message("✅ FFmpeg найден в PATH")
            return True
    except:
        pass
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    """Установка FFmpeg на Windows"""
    try:
        log_message("🚀 Установка FFmpeg для Windows...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(TOOLS_DIR, "ffmpeg.zip")
        extract_path = os.path.join(TOOLS_DIR, "ffmpeg_temp")
        
        log_message("📥 Скачивание FFmpeg...")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        log_message("📦 Распаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку bin
        for item in os.listdir(extract_path):
            if item.startswith("ffmpeg-") and os.path.isdir(os.path.join(extract_path, item)):
                bin_path = os.path.join(extract_path, item, "bin")
                target_path = os.path.join(TOOLS_DIR, "ffmpeg", "bin")
                
                if os.path.exists(target_path):
                    shutil.rmtree(target_path, ignore_errors=True)
                
                os.makedirs(target_path, exist_ok=True)
                
                # Копируем файлы
                for file in os.listdir(bin_path):
                    src = os.path.join(bin_path, file)
                    dst = os.path.join(target_path, file)
                    shutil.copy2(src, dst)
                break
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        # Обновляем PATH
        os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ FFmpeg установлен успешно")
        return True
        
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def install_ffmpeg():
    """Установка FFmpeg в зависимости от ОС"""
    if platform.system() == "Windows":
        return install_ffmpeg_windows()
    else:
        log_message(f"⚠️ Автоустановка для {platform.system()} не поддерживается", "WARNING")
        log_message("Установите FFmpeg вручную: https://ffmpeg.org/download.html", "WARNING")
        return False

# ==================== УСТАНОВКА NODE.JS ДЛЯ WINDOWS ====================
def check_nodejs() -> bool:
    """Проверка наличия Node.js"""
    try:
        # Проверяем в tools папке
        if platform.system() == "Windows":
            node_exe = os.path.join(NODE_PATH, "node.exe")
        else:
            node_exe = os.path.join(NODE_PATH, "bin", "node")
        
        if os.path.exists(node_exe):
            log_message(f"✅ Node.js найден: {node_exe}")
            return True
        
        # Проверяем в PATH
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
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
        log_message("🚀 Установка Node.js для Windows...")
        
        node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip"
        zip_path = os.path.join(TOOLS_DIR, "nodejs.zip")
        extract_path = os.path.join(TOOLS_DIR, "nodejs_temp")
        
        log_message("📥 Скачивание Node.js...")
        urllib.request.urlretrieve(node_url, zip_path)
        
        log_message("📦 Распаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку
        for item in os.listdir(extract_path):
            if item.startswith("node-v") and os.path.isdir(os.path.join(extract_path, item)):
                source_path = os.path.join(extract_path, item)
                target_path = NODE_PATH
                
                if os.path.exists(target_path):
                    shutil.rmtree(target_path, ignore_errors=True)
                
                shutil.copytree(source_path, target_path)
                break
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path, ignore_errors=True)
        
        # Обновляем PATH
        os.environ['PATH'] = NODE_PATH + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ Node.js установлен успешно")
        return True
        
    except Exception as e:
        log_message(f"Ошибка установки Node.js: {e}", "ERROR")
        return False

def install_nodejs():
    """Установка Node.js в зависимости от ОС"""
    if platform.system() == "Windows":
        return install_nodejs_windows()
    else:
        log_message(f"⚠️ Автоустановка для {platform.system()} не поддерживается", "WARNING")
        return False

def auto_install_all():
    """Автоматическая установка всех зависимостей"""
    log_message("=" * 50)
    log_message("🔧 ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ")
    log_message("=" * 50)
    
    # Установка FFmpeg
    if not check_ffmpeg():
        log_message("⚠️ Устанавливаю FFmpeg...")
        install_ffmpeg()
    else:
        log_message("✅ FFmpeg уже установлен")
    
    # Установка Node.js
    if not check_nodejs():
        log_message("⚠️ Устанавливаю Node.js...")
        install_nodejs()
    else:
        log_message("✅ Node.js уже установлен")
    
    # Обновление yt-dlp
    try:
        log_message("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
        log_message("✅ yt-dlp обновлён")
    except Exception as e:
        log_message(f"Ошибка обновления yt-dlp: {e}", "WARNING")
    
    log_message("=" * 50)
    log_message("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    log_message("=" * 50)

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    """Сжатие видео до указанного размера"""
    try:
        ffmpeg_exe = "ffmpeg"
        ffprobe_exe = "ffprobe"
        
        # Используем локальную версию если есть
        if platform.system() == "Windows":
            local_ffmpeg = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
            local_ffprobe = os.path.join(FFMPEG_PATH, "ffprobe.exe")
            if os.path.exists(local_ffmpeg):
                ffmpeg_exe = local_ffmpeg
                ffprobe_exe = local_ffprobe
        
        # Получаем длительность видео
        probe_cmd = [
            ffprobe_exe, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0 or not result.stdout:
            log_message(f"Ошибка получения длительности: {result.stderr}", "ERROR")
            return None
        
        duration = float(result.stdout.strip())
        if duration <= 0:
            duration = 60
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 3000000))
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Команда сжатия
        compress_cmd = [
            ffmpeg_exe, '-i', input_path,
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
            log_message(f"❌ Ошибка сжатия", "ERROR")
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
            log_message(f"✅ Из кэша: {cached['title'][:50]}")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {url[:50]}... | {quality}")
    
    try:
        # Настройки качества
        quality_map = {
            "144p": 'worstvideo[height<=144]+worstaudio/best[height<=144]',
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
            
            if not info:
                log_message("❌ Не удалось получить информацию", "ERROR")
                return None, None, False
            
            # Получаем заголовок
            title = info.get('title', 'video')
            if not title:
                title = 'video'
            
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
                    log_message(f"Найден файл: {os.path.basename(filename)}")
                else:
                    log_message("❌ Файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:50]}... ({file_size:.1f} МБ)")
            
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
            log_message(f"✅ Отправлено без сжатия ({file_size_mb:.1f} МБ)")
            return True
        
        log_message(f"📦 Видео {file_size_mb:.1f} МБ > {LIMIT} МБ, сжимаю...")
        status_msg = await message.answer(
            f"📦 *Видео слишком большое* ({file_size_mb:.1f} МБ)\n"
            f"⏳ Сжимаю до 48 МБ...\n"
            f"_Это может занять 2-5 минут_",
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
                await status_msg.edit_text(
                    f"❌ *Не удалось сжать видео*\n"
                    f"Получилось {new_size:.1f} МБ\n"
                    f"Попробуйте качество ниже",
                    parse_mode=ParseMode.MARKDOWN
                )
                return False
        else:
            await status_msg.edit_text(
                "❌ *Ошибка сжатия*\n"
                "Попробуйте качество ниже (720p или 480p)",
                parse_mode=ParseMode.MARKDOWN
            )
            return False
            
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
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
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте ссылку на видео с YouTube, TikTok, Instagram.\n\n"
        "*Особенности:*\n"
        "• ✅ Автоустановка FFmpeg и Node.js\n"
        "• 🗜️ Автосжатие видео до 50 МБ\n"
        "• ⚡ Кэширование\n\n"
        "*Команды:*\n"
        "/start - Главное меню\n"
        "/help - Помощь\n"
        "/stats - Статистика\n"
        "/clear - Очистить кэш\n"
        "/log - Логи",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "1️⃣ Скопируйте ссылку на видео\n"
        "2️⃣ Отправьте её боту\n"
        "3️⃣ Выберите качество\n"
        "4️⃣ Видео >50 МБ сожмётся автоматически\n\n"
        "*Совет:* Для больших видео выбирайте 720p",
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
        await message.answer("📋 Логов пока нет")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    node_status = "✅" if check_nodejs() else "❌"
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🗜️ FFmpeg: {ffmpeg_status}\n"
        f"📦 Node.js: {node_status}",
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
        
        status_msg = await callback.message.edit_text(
            f"⏳ *Скачиваю {quality_name}...*\nПожалуйста, подождите",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ *Не удалось скачать видео*\nПопробуйте другое качество",
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
            await status_msg.edit_text("❌ *Не удалось скачать аудио*", parse_mode=ParseMode.MARKDOWN)
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
            log_message(f"Ошибка: {e}", "ERROR")
            await status_msg.edit_text(f"❌ *Ошибка:* `{str(e)[:100]}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("📦 АВТОМАТИЧЕСКАЯ УСТАНОВКА ЗАВИСИМОСТЕЙ")
    print("=" * 60)
    
    auto_install_all()
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"🗜️ Папка сжатия: {os.path.abspath(COMPRESSED_DIR)}")
    print(f"🔧 Папка инструментов: {os.path.abspath(TOOLS_DIR)}")
    print("=" * 60)
    print("✅ БОТ ГОТОВ!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
