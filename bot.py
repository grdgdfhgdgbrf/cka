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

# Создаём все необходимые папки
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
FFMPEG_DIR = os.path.join(TOOLS_DIR, "ffmpeg")
NODE_DIR = os.path.join(TOOLS_DIR, "nodejs")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COMPRESSED_DIR = os.path.join(BASE_DIR, "compressed")
CACHE_FILE = os.path.join(BASE_DIR, "video_cache.json")
LOG_FILE = os.path.join(BASE_DIR, "bot_log.txt")

for dir_name in [TOOLS_DIR, FFMPEG_DIR, NODE_DIR, DOWNLOAD_DIR, COMPRESSED_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# Добавляем tools в PATH
os.environ['PATH'] = os.path.join(FFMPEG_DIR, "bin") + os.pathsep + \
                      os.path.join(NODE_DIR) + os.pathsep + \
                      os.environ.get('PATH', '')

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

# ==================== АВТОУСТАНОВКА FFMPEG ====================
def download_file(url, dest):
    """Скачивание файла с прогрессом"""
    log_message(f"Скачивание: {url}")
    urllib.request.urlretrieve(url, dest)
    return dest

def install_ffmpeg():
    """Установка FFmpeg в папку бота"""
    try:
        log_message("🚀 Установка FFmpeg в папку бота...")
        
        # Определяем системную архитектуру
        if platform.machine().endswith('64'):
            arch = "64"
        else:
            arch = "32"
        
        # Скачиваем FFmpeg
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(TOOLS_DIR, "ffmpeg.zip")
        
        download_file(ffmpeg_url, zip_path)
        
        # Распаковываем
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(TOOLS_DIR)
        
        # Находим распакованную папку
        for item in os.listdir(TOOLS_DIR):
            if item.startswith("ffmpeg-") and os.path.isdir(os.path.join(TOOLS_DIR, item)):
                src_bin = os.path.join(TOOLS_DIR, item, "bin")
                if os.path.exists(src_bin):
                    # Копируем файлы в FFMPEG_DIR/bin
                    target_bin = os.path.join(FFMPEG_DIR, "bin")
                    if not os.path.exists(target_bin):
                        os.makedirs(target_bin)
                    
                    for file in os.listdir(src_bin):
                        src_file = os.path.join(src_bin, file)
                        dst_file = os.path.join(target_bin, file)
                        shutil.copy2(src_file, dst_file)
                    
                    # Удаляем временную папку
                    shutil.rmtree(os.path.join(TOOLS_DIR, item))
                break
        
        # Удаляем zip
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        # Обновляем PATH
        os.environ['PATH'] = os.path.join(FFMPEG_DIR, "bin") + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ FFmpeg установлен успешно")
        return True
        
    except Exception as e:
        log_message(f"❌ Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def check_ffmpeg():
    """Проверка FFmpeg"""
    ffmpeg_path = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
    if os.path.exists(ffmpeg_path):
        log_message(f"✅ FFmpeg найден: {ffmpeg_path}")
        return True
    return False

# ==================== АВТОУСТАНОВКА NODE.JS ====================
def install_nodejs():
    """Установка Node.js в папку бота"""
    try:
        log_message("🚀 Установка Node.js в папку бота...")
        
        # Скачиваем Node.js (встроенный, не требует установки)
        if platform.machine().endswith('64'):
            node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip"
        else:
            node_url = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x86.zip"
        
        zip_path = os.path.join(TOOLS_DIR, "nodejs.zip")
        download_file(node_url, zip_path)
        
        # Распаковываем
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(TOOLS_DIR)
        
        # Находим распакованную папку
        for item in os.listdir(TOOLS_DIR):
            if item.startswith("node-v") and os.path.isdir(os.path.join(TOOLS_DIR, item)):
                src_dir = os.path.join(TOOLS_DIR, item)
                # Копируем содержимое в NODE_DIR
                for file in os.listdir(src_dir):
                    src_file = os.path.join(src_dir, file)
                    dst_file = os.path.join(NODE_DIR, file)
                    if os.path.isdir(src_file):
                        if os.path.exists(dst_file):
                            shutil.rmtree(dst_file)
                        shutil.copytree(src_file, dst_file)
                    else:
                        shutil.copy2(src_file, dst_file)
                # Удаляем временную папку
                shutil.rmtree(src_dir)
                break
        
        # Удаляем zip
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        # Обновляем PATH
        os.environ['PATH'] = NODE_DIR + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ Node.js установлен успешно")
        return True
        
    except Exception as e:
        log_message(f"❌ Ошибка установки Node.js: {e}", "ERROR")
        return False

def check_nodejs():
    """Проверка Node.js"""
    node_path = os.path.join(NODE_DIR, "node.exe")
    if os.path.exists(node_path):
        log_message(f"✅ Node.js найден: {node_path}")
        return True
    return False

# ==================== ОБНОВЛЕНИЕ YT-DLP ====================
def update_ytdlp():
    """Обновление yt-dlp"""
    try:
        log_message("🔄 Обновление yt-dlp...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp', '--quiet'])
        log_message("✅ yt-dlp обновлён")
        return True
    except Exception as e:
        log_message(f"⚠️ Ошибка обновления yt-dlp: {e}", "WARNING")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    """Сжатие видео с использованием встроенного FFmpeg"""
    try:
        ffmpeg_path = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
        ffprobe_path = os.path.join(FFMPEG_DIR, "bin", "ffprobe.exe")
        
        if not os.path.exists(ffmpeg_path):
            log_message("❌ FFmpeg не найден", "ERROR")
            return None
        
        # Получаем длительность видео
        probe_cmd = [
            ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip()) if result.stdout else 60
        
        if duration <= 0:
            duration = 60
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 2000000))  # 0.3-2 Mbps
        
        # Выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Сжатие
        compress_cmd = [
            ffmpeg_path, '-i', input_path,
            '-b:v', f'{video_bitrate}',
            '-b:a', '96k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"Сжатие: битрейт {video_bitrate} bps, длительность {duration} сек")
        
        result = subprocess.run(compress_cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"❌ Ошибка сжатия: {result.stderr[:200]}", "ERROR")
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
        
        # Путь к node.exe если есть
        node_path = os.path.join(NODE_DIR, "node.exe")
        
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
        
        # Если есть Node.js, используем его
        if os.path.exists(node_path):
            opts['ffmpeg_location'] = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
        
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
        # Если файл меньше лимита - отправляем сразу
        if file_size_mb <= LIMIT:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Отправлено без сжатия ({file_size_mb:.1f} МБ)")
            return True
        
        # Если файл больше - сжимаем
        log_message(f"📦 Видео {file_size_mb:.1f} МБ > {LIMIT} МБ, сжимаю...")
        status_msg = await message.answer(f"📦 *Видео слишком большое* ({file_size_mb:.1f} МБ)\n⏳ Сжимаю до 48 МБ...\n_Это может занять 2-5 минут_", parse_mode=ParseMode.MARKDOWN)
        
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
                
                # Удаляем сжатый файл
                try:
                    os.remove(compressed_path)
                except:
                    pass
                return True
            else:
                await status_msg.edit_text(f"❌ *Не удалось сжать видео*\nПолучилось {new_size:.1f} МБ\nПопробуйте качество ниже.", parse_mode=ParseMode.MARKDOWN)
                return False
        else:
            await status_msg.edit_text("❌ *Ошибка сжатия*\nПопробуйте выбрать качество ниже (720p или 480p)", parse_mode=ParseMode.MARKDOWN)
            return False
            
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
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
         InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте мне ссылку на видео с YouTube, TikTok, Instagram и других сайтов.\n\n"
        "*Особенности:*\n"
        "• Автоматическое сжатие видео до 50 МБ\n"
        "• Кэширование - повторные видео мгновенно\n"
        "• Не требует установки FFmpeg или Node.js\n\n"
        "*Команды:*\n"
        "/start - Главное меню\n"
        "/help - Помощь\n"
        "/stats - Статистика\n"
        "/clear - Очистить кэш\n"
        "/check - Проверить установку",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "1️⃣ Скопируйте ссылку на видео\n"
        "2️⃣ Отправьте её боту\n"
        "3️⃣ Выберите качество\n"
        "4️⃣ Если видео >50 МБ - автоматически сожмётся\n\n"
        "*Совет:* Для больших видео выбирайте 720p или 480p\n\n"
        "📋 /log - Показать логи ошибок",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("log"))
async def log_cmd(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            log_text = "".join(last_lines)
            await message.answer(f"📋 *Последние логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
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
        f"📁 В кэше: {len(video_cache)} видео\n"
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

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    status_msg = await message.answer("🔍 *Проверка системы...*", parse_mode=ParseMode.MARKDOWN)
    
    ffmpeg_ok = check_ffmpeg()
    node_ok = check_nodejs()
    
    if not ffmpeg_ok:
        await status_msg.edit_text("⚠️ *Установка FFmpeg...*", parse_mode=ParseMode.MARKDOWN)
        install_ffmpeg()
        ffmpeg_ok = check_ffmpeg()
    
    if not node_ok:
        await status_msg.edit_text("⚠️ *Установка Node.js...*", parse_mode=ParseMode.MARKDOWN)
        install_nodejs()
        node_ok = check_nodejs()
    
    update_ytdlp()
    
    status = (
        f"✅ *Система готова!*\n\n"
        f"FFmpeg: {'✅' if ffmpeg_ok else '❌'}\n"
        f"Node.js: {'✅' if node_ok else '❌'}\n"
        f"yt-dlp: {'✅'}\n\n"
        f"📁 Все инструменты установлены в папку `tools`"
    )
    await status_msg.edit_text(status, parse_mode=ParseMode.MARKDOWN)

# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ *Отправьте ссылку на видео*\nСсылка должна начинаться с http:// или https://", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(
        "🎥 *Выберите качество:*\n\n"
        "💡 *Совет:* Если видео большое, выберите 720p - оно сожмётся автоматически",
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
        
        status_msg = await callback.message.edit_text(f"⏳ *Скачиваю {quality_name}...*\nПожалуйста, подождите", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ *Не удалось скачать видео*\nПопробуйте другое качество или ссылку", parse_mode=ParseMode.MARKDOWN)
            await callback.answer()
            return
        
        await status_msg.edit_text(f"📤 *Обработка видео...*", parse_mode=ParseMode.MARKDOWN)
        
        success = await send_video_with_compress(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await status_msg.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.answer("❌ Ошибка отправки")
        
    elif action == "audio":
        url = parts[1]
        
        status_msg = await callback.message.edit_text("⏳ *Скачиваю аудио (MP3)...*", parse_mode=ParseMode.MARKDOWN)
        
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
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("📦 Автоустановка FFmpeg и Node.js")
    print("=" * 50)
    
    # Установка всего необходимого
    if not check_ffmpeg():
        print("⚠️ Установка FFmpeg...")
        install_ffmpeg()
    else:
        print("✅ FFmpeg уже установлен")
    
    if not check_nodejs():
        print("⚠️ Установка Node.js...")
        install_nodejs()
    else:
        print("✅ Node.js уже установлен")
    
    # Обновляем yt-dlp
    update_ytdlp()
    
    print(f"📁 Папка бота: {BASE_DIR}")
    print(f"📁 Папка инструментов: {TOOLS_DIR}")
    print("=" * 50)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
