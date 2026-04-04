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
import tempfile
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "ВАШ_ТОКЕН_СЮДА"

# Создаем все необходимые папки
for dir_name in ["downloads", "compressed", "ffmpeg_bin", "temp"]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА FFMPEG ====================
def get_ffmpeg_path():
    """Получить путь к ffmpeg.exe"""
    possible_paths = [
        os.path.join(os.getcwd(), "ffmpeg_bin", "ffmpeg.exe"),
        os.path.join(os.getcwd(), "ffmpeg", "bin", "ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "ffmpeg.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def check_ffmpeg():
    """Проверка наличия FFmpeg"""
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        try:
            result = subprocess.run([ffmpeg_path, '-version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✅ FFmpeg найден: {ffmpeg_path}")
                return True
        except:
            pass
    print("❌ FFmpeg не найден")
    return False

def download_ffmpeg():
    """Скачивание FFmpeg с GitHub"""
    try:
        print("🚀 Скачивание FFmpeg...")
        
        # Используем стабильную сборку с GitHub
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg_temp.zip")
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        print("✅ FFmpeg скачан")
        
        # Распаковка
        print("📦 Распаковка FFmpeg...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("ffmpeg_temp")
        
        # Поиск ffmpeg.exe
        for root, dirs, files in os.walk("ffmpeg_temp"):
            if "ffmpeg.exe" in files:
                source_path = os.path.join(root, "ffmpeg.exe")
                target_path = os.path.join(os.getcwd(), "ffmpeg_bin", "ffmpeg.exe")
                
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_path, target_path)
                print(f"✅ FFmpeg скопирован в {target_path}")
                break
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree("ffmpeg_temp", ignore_errors=True)
        
        return get_ffmpeg_path() is not None
        
    except Exception as e:
        print(f"❌ Ошибка скачивания FFmpeg: {e}")
        return False

def auto_install_ffmpeg():
    """Автоматическая установка FFmpeg"""
    if check_ffmpeg():
        return True
    
    print("⚠️ FFmpeg не найден, начинаю автоматическую установку...")
    return download_ffmpeg()

# ==================== СЖАТИЕ ВИДЕО ====================
def get_video_duration(file_path):
    """Получение длительности видео"""
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return 60
    
    cmd = [
        ffmpeg_path, '-i', file_path,
        '-f', 'null', '-'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Парсим длительность из вывода
        for line in result.stderr.split('\n'):
            if 'Duration' in line:
                import re
                match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                if match:
                    hours, minutes, seconds = match.groups()
                    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except:
        pass
    return 60

def compress_video(input_path, target_size_mb=48):
    """Сжатие видео до целевого размера"""
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        print("❌ FFmpeg не найден для сжатия")
        return None
    
    try:
        # Получаем длительность
        duration = get_video_duration(input_path)
        
        # Рассчитываем битрейт
        target_bits = target_size_mb * 8 * 1024 * 1024
        video_bitrate = int(target_bits / duration)
        video_bitrate = max(300000, min(video_bitrate, 2000000))  # 0.3-2 Mbps
        
        # Создаем выходной файл
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join("compressed", f"{name_without_ext}_compressed.mp4")
        
        # Команда сжатия
        cmd = [
            ffmpeg_path, '-i', input_path,
            '-c:v', 'libx264',
            '-b:v', f'{video_bitrate}',
            '-maxrate', f'{int(video_bitrate * 1.5)}',
            '-bufsize', f'{video_bitrate * 2}',
            '-c:a', 'aac',
            '-b:a', '96k',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        
        print(f"Сжатие: битрейт {video_bitrate} bps, длительность {duration} сек")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"✅ Сжато: {new_size:.1f} МБ")
            return output_path
        else:
            print(f"❌ Ошибка сжатия: {result.stderr[:200]}")
            return None
            
    except Exception as e:
        print(f"Ошибка сжатия: {e}")
        return None

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

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео"""
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title'][:50]}")
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
            'outtmpl': os.path.join("downloads", '%(title)s.%(ext)s'),
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
            for f in os.listdir("downloads"):
                if f.endswith('.mp4') and title in f:
                    filename = os.path.join("downloads", f)
                    break
            
            if not filename:
                mp4_files = [os.path.join("downloads", f) for f in os.listdir("downloads") if f.endswith('.mp4')]
                if mp4_files:
                    filename = max(mp4_files, key=os.path.getmtime)
                else:
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
            'outtmpl': os.path.join("downloads", '%(title)s.%(ext)s'),
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
            for f in os.listdir("downloads"):
                if f.endswith('.mp3') and title in f:
                    filename = os.path.join("downloads", f)
                    break
            
            if not filename:
                mp3_files = [os.path.join("downloads", f) for f in os.listdir("downloads") if f.endswith('.mp3')]
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
        
        # Сжатие в отдельном потоке
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
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "📹 Отправьте мне ссылку на видео с YouTube, TikTok, Instagram.\n\n"
        "*Особенности:*\n"
        "• ✅ Автоустановка FFmpeg\n"
        "• 🗜️ Автоматическое сжатие видео до 50 МБ\n"
        "• ⚡ Кэширование - повторные видео мгновенно\n\n"
        "*Команды:*\n"
        "/start - Главное меню\n"
        "/help - Помощь\n"
        "/stats - Статистика\n"
        "/clear - Очистить кэш",
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
        "*Совет:* Для больших видео выбирайте 720p или 480p",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)} видео\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🗜️ FFmpeg: {ffmpeg_status}",
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
    print("📦 Автоматическая установка FFmpeg")
    print("=" * 50)
    
    # Автоустановка FFmpeg
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, устанавливаю...")
        auto_install_ffmpeg()
    
    if check_ffmpeg():
        print("✅ FFmpeg готов к работе")
    else:
        print("❌ Ошибка установки FFmpeg")
    
    print(f"📁 Папка загрузок: {os.path.abspath('downloads')}")
    print("=" * 50)
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
