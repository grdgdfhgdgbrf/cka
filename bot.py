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
log_message(f"Загружено {len(video_cache)} записей")

# ==================== УСТАНОВКА FFMPEG ====================
def check_ffmpeg() -> bool:
    try:
        # Проверяем в PATH
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message("✅ FFmpeg найден")
            return True
    except:
        pass
    
    # Проверяем в C:\ffmpeg
    ffmpeg_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"ffmpeg.exe"
    ]
    
    for path in ffmpeg_paths:
        if os.path.exists(path):
            bin_dir = os.path.dirname(path)
            os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
            log_message(f"✅ FFmpeg найден: {path}")
            return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg():
    try:
        log_message("🚀 Установка FFmpeg...")
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = "ffmpeg.zip"
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Находим папку с ffmpeg.exe
        for item in os.listdir("."):
            if item.startswith("ffmpeg-") and os.path.isdir(item):
                bin_path = os.path.join(item, "bin")
                if os.path.exists(bin_path):
                    target = r"C:\ffmpeg"
                    if os.path.exists(target):
                        shutil.rmtree(target, ignore_errors=True)
                    shutil.copytree(bin_path, os.path.join(target, "bin"))
                    shutil.rmtree(item, ignore_errors=True)
                    break
        
        os.remove(zip_path)
        os.environ['PATH'] = r"C:\ffmpeg\bin" + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ FFmpeg установлен")
        return True
    except Exception as e:
        log_message(f"Ошибка установки: {e}", "ERROR")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    """
    Сжатие видео до указанного размера (МБ)
    Возвращает путь к сжатому файлу
    """
    try:
        if not check_ffmpeg():
            log_message("❌ FFmpeg не найден для сжатия", "ERROR")
            return None
        
        # Получаем информацию о видео
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration', 
            '-of', 'default=noprint_wrappers=1', input_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        info = {}
        for line in result.stdout.split('\n'):
            if '=' in line:
                k, v = line.split('=')
                info[k] = float(v) if k == 'duration' else int(v)
        
        duration = info.get('duration', 60)
        width = info.get('width', 1920)
        height = info.get('height', 1080)
        
        # Определяем битрейт для целевого размера
        # Размер = (битрейт * длительность) / 8
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        
        # Ограничиваем битрейт разумными значениями
        video_bitrate = max(500000, min(video_bitrate, 5000000))  # 0.5-5 Mbps
        
        # Определяем разрешение для сжатия
        if height > 720:
            new_height = 720
            new_width = int(width * new_height / height)
        elif height > 480:
            new_height = 480
            new_width = int(width * new_height / height)
        else:
            new_width = width
            new_height = height
        
        # Путь для сжатого файла
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(COMPRESSED_DIR, f"{name_without_ext}_compressed.mp4")
        
        # Сжатие через FFmpeg
        compress_cmd = [
            'ffmpeg', '-i', input_path,
            '-vf', f'scale={new_width}:{new_height}',
            '-b:v', f'{video_bitrate}',
            '-b:a', '128k',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        
        log_message(f"Сжатие: {input_path} -> {output_path}")
        log_message(f"Битрейт: {video_bitrate} bps, разрешение: {new_width}x{new_height}")
        
        result = subprocess.run(compress_cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"❌ Ошибка сжатия: {result.stderr}", "ERROR")
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
            log_message(f"✅ Из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {url} | {quality}")
    
    try:
        # Настройки качества
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
    """Отправка видео с автоматическим сжатием при превышении лимита"""
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT = 49  # Оставляем 1 МБ запаса
    
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
        await message.answer(f"📦 Видео слишком большое ({file_size_mb:.1f} МБ), сжимаю до 48 МБ...\n⏳ Это может занять 2-5 минут")
        
        compressed_path = await asyncio.get_event_loop().run_in_executor(
            None, compress_video, file_path, 48
        )
        
        if compressed_path and os.path.exists(compressed_path):
            new_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if new_size <= LIMIT:
                video_file = FSInputFile(compressed_path)
                await message.answer_video(
                    video=video_file,
                    caption=f"✅ *{title[:80]}*{cache_text} 🗜️(сжато)\n📹 {quality} | {new_size:.1f} МБ (было {file_size_mb:.1f} МБ)",
                    parse_mode=ParseMode.MARKDOWN
                )
                log_message(f"✅ Отправлено со сжатием ({new_size:.1f} МБ)")
                
                # Удаляем сжатый файл после отправки
                os.remove(compressed_path)
                return True
            else:
                log_message(f"❌ После сжатия всё ещё {new_size:.1f} МБ", "ERROR")
                await message.answer(f"❌ Не удалось сжать видео до 50 МБ (получилось {new_size:.1f} МБ). Попробуйте качество ниже.")
                return False
        else:
            await message.answer(f"❌ Не удалось сжать видео. Попробуйте выбрать качество ниже.")
            return False
            
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
        return False

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p (маленькое)", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="🎬 720p (рекомендуется)", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Лучшее качество", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3 (аудио)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот с автоматическим сжатием*\n\n"
        "📦 *Особенности:*\n"
        "• Автоматическое сжатие видео до 50 МБ\n"
        "• Поддержка любых размеров\n"
        "• Кэширование - повторные видео мгновенно\n\n"
        "📹 *Как работает:*\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите качество\n"
        "3. Если видео >50 МБ - автоматически сожмётся\n\n"
        "📋 /log — Логи\n"
        "🗑️ /clear — Очистить кэш\n"
        "📊 /stats — Статистика",
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
        await message.answer("Логов пока нет")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} видео\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🗜️ FFmpeg: {'✅' if check_ffmpeg() else '❌'}",
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
    await message.answer(f"🗑️ Очищено {deleted} файлов")

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        await message.answer("⚠️ Устанавливаю FFmpeg...")
        install_ffmpeg()
        ffmpeg_ok = check_ffmpeg()
    
    await message.answer(
        f"✅ *Система готова*\n\n"
        f"FFmpeg: {'✅ Установлен' if ffmpeg_ok else '❌ Ошибка'}\n"
        f"Сжатие видео: {'✅ Доступно' if ffmpeg_ok else '❌ Недоступно'}",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку на видео")
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
        
        quality_names = {
            "144p": "144p", "240p": "240p", "360p": "360p",
            "480p": "480p", "720p": "720p", "1080p": "1080p", "best": "лучшее"
        }
        quality_name = quality_names.get(quality, quality)
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality_name}*...\nПожалуйста, подождите", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text("❌ Не удалось скачать видео.\nПопробуйте другое качество или ссылку.")
            await callback.answer()
            return
        
        await callback.message.edit_text(f"📤 Обработка видео...")
        
        success = await send_video_with_compress(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await callback.message.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.answer("Ошибка отправки")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио (MP3)...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Не удалось скачать аудио")
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
            await callback.message.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            log_message(f"Ошибка: {e}", "ERROR")
            await callback.message.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("📦 Включено автоматическое сжатие видео")
    print("=" * 50)
    
    if not check_ffmpeg():
        print("⚠️ Устанавливаю FFmpeg...")
        install_ffmpeg()
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"🗜️ Сжатие: {os.path.abspath(COMPRESSED_DIR)}")
    print("=" * 50)
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
