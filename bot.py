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

# ==================== ИСПРАВЛЕННАЯ УСТАНОВКА FFMPEG ====================
def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg"""
    try:
        # Проверяем через where
        result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            log_message(f"✅ FFmpeg найден: {result.stdout.strip().split()[0]}")
            return True
    except:
        pass
    
    # Проверяем через ffmpeg команду
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            log_message("✅ FFmpeg работает")
            return True
    except:
        pass
    
    # Проверяем в стандартных папках
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg.exe"
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            bin_dir = os.path.dirname(path)
            os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
            log_message(f"✅ FFmpeg найден: {path}")
            return True
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg():
    """Установка FFmpeg"""
    try:
        log_message("🚀 Установка FFmpeg...")
        
        # Скачиваем
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg.zip")
        
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        log_message("✅ Скачано")
        
        # Распаковываем
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Находим папку с ffmpeg.exe
        for item in os.listdir("."):
            if item.startswith("ffmpeg-") and os.path.isdir(item):
                bin_path = os.path.join(item, "bin")
                if os.path.exists(bin_path):
                    # Создаем папку C:\ffmpeg
                    target = r"C:\ffmpeg"
                    if not os.path.exists(target):
                        os.makedirs(target)
                    
                    # Копируем bin папку
                    target_bin = os.path.join(target, "bin")
                    if os.path.exists(target_bin):
                        shutil.rmtree(target_bin, ignore_errors=True)
                    
                    shutil.copytree(bin_path, target_bin)
                    log_message(f"✅ FFmpeg скопирован в {target_bin}")
                    
                    # Добавляем в PATH
                    os.environ['PATH'] = target_bin + os.pathsep + os.environ.get('PATH', '')
                    
                    # Удаляем временные файлы
                    shutil.rmtree(item, ignore_errors=True)
                    break
        
        os.remove(zip_path)
        log_message("✅ FFmpeg установлен")
        return check_ffmpeg()
        
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, target_size_mb: int = 48) -> str:
    """Сжатие видео до нужного размера с помощью FFmpeg"""
    try:
        if not check_ffmpeg():
            log_message("FFmpeg не найден, сжатие невозможно", "ERROR")
            return None
        
        input_size = os.path.getsize(input_path) / (1024 * 1024)
        if input_size <= target_size_mb:
            log_message(f"Видео уже меньше {target_size_mb} МБ, сжатие не нужно")
            return input_path
        
        log_message(f"Сжатие видео: {input_size:.1f} МБ -> {target_size_mb} МБ")
        
        # Создаем имя для сжатого файла
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed.mp4"
        
        # Расчет битрейта
        duration = get_video_duration(input_path)
        if duration:
            # Целевой битрейт (бит/с) с запасом 10%
            target_bitrate = int((target_size_mb * 8 * 1024 * 1024) / duration * 0.9)
            # Ограничиваем битрейт
            target_bitrate = max(500000, min(target_bitrate, 5000000))  # 500k-5M бит/с
        else:
            target_bitrate = 1000000  # 1 Мбит/с по умолчанию
        
        # Команда сжатия
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',
            '-b:v', f'{target_bitrate}',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-preset', 'fast',
            '-movflags', '+faststart',
            '-y', output_path
        ]
        
        log_message(f"Запуск сжатия: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжатие завершено: {new_size:.1f} МБ")
            return output_path
        else:
            log_message(f"Ошибка сжатия: {result.stderr[:200]}", "ERROR")
            return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
        return None

def get_video_duration(file_path: str) -> float:
    """Получение длительности видео в секундах"""
    try:
        cmd = ['ffmpeg', '-i', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stderr.split('\n'):
            if 'Duration' in line:
                time_str = line.split('Duration: ')[1].split(',')[0]
                h, m, s = map(float, time_str.split(':'))
                return h * 3600 + m * 60 + s
    except:
        pass
    return None

# ==================== СКАЧИВАНИЕ ВИДЕО ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео"""
    video_id = hashlib.md5(f"{url}_{quality}".encode()).hexdigest()
    
    # Проверка кэша
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    log_message(f"Скачивание: {quality} | {url}")
    
    try:
        # Форматы для YouTube
        format_map = {
            "144p": "worst[height<=144]",
            "240p": "best[height<=240]", 
            "360p": "best[height<=360]",
            "480p": "best[height<=480]",
            "720p": "best[height<=720]",
            "1080p": "best[height<=1080]",
            "best": "best"
        }
        format_spec = format_map.get(quality, "best[height<=720]")
        
        opts = {
            'format': format_spec,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s_%(height)sp.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
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
                if f.endswith('.mp4') and (title in f or title[:30] in f):
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    break
            
            if not filename:
                mp4_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')]
                if mp4_files:
                    filename = max(mp4_files, key=os.path.getmtime)
            
            if not filename:
                return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title[:50]}..., {file_size:.1f} МБ")
            
            # Сохраняем в кэш
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
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
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
            
            if filename:
                video_cache[audio_id] = {
                    'path': filename,
                    'title': title,
                    'type': 'audio',
                    'url': url,
                    'date': datetime.now().isoformat()
                }
                save_cache(video_cache)
                return filename, title, False
            
            return None, None, False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА ФАЙЛОВ ====================
async def send_file_auto(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    """Отправка файла с автоматическим сжатием"""
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " ⚡(кэш)" if from_cache else ""
    
    # Если файл больше 50 МБ, пробуем сжать
    if file_size_mb > 50:
        log_message(f"Файл {file_size_mb:.1f} МБ превышает лимит, сжимаю...")
        await message.answer(f"📦 Видео весит {file_size_mb:.1f} МБ (лимит 50 МБ). Сжимаю...\nЭто может занять 2-3 минуты.")
        
        compressed_path = await asyncio.get_event_loop().run_in_executor(None, compress_video, file_path, 48)
        
        if compressed_path and os.path.exists(compressed_path):
            file_path = compressed_path
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            log_message(f"После сжатия: {file_size_mb:.1f} МБ")
            await message.answer(f"✅ Сжатие завершено! Теперь файл весит {file_size_mb:.1f} МБ")
        else:
            # Если сжать не удалось, отправляем как документ
            await message.answer(f"⚠️ Не удалось сжать видео. Отправляю как файл (можно скачать).")
            doc_file = FSInputFile(file_path)
            await message.answer_document(
                document=doc_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n⚠️ Видео >50 МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            return True
    
    # Отправка видео (если меньше 50 МБ или после сжатия)
    try:
        if file_size_mb <= 50:
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Видео отправлено ({file_size_mb:.1f} МБ)")
        else:
            # Запасной вариант - как документ
            doc_file = FSInputFile(file_path)
            await message.answer_document(
                document=doc_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Файл отправлен ({file_size_mb:.1f} МБ)")
        return True
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
        await message.answer(f"❌ Ошибка отправки: {str(e)[:100]}")
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
        "Отправьте ссылку на видео с YouTube, Instagram, TikTok и др.\n\n"
        "⚡ *Особенности:*\n"
        "• Автоматическое сжатие видео до 50 МБ\n"
        "• Кэширование - повторные видео мгновенно\n"
        "• Поддержка файлов до 2 ГБ\n\n"
        "📋 /log — Логи\n"
        "🗑️ /clear — Очистить кэш\n"
        "📊 /stats — Статистика\n"
        "🔧 /check — Проверить FFmpeg",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("log"))
async def log_cmd(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            await message.answer(f"📋 *Логи:*\n```\n{''.join(last_lines)[:3000]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Логов пока нет")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    ffmpeg_status = "✅" if check_ffmpeg() else "❌"
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"🔧 FFmpeg: {ffmpeg_status}",
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
        await message.answer("⚠️ Установка FFmpeg...")
        ffmpeg_ok = install_ffmpeg()
    
    status = "✅ FFmpeg готов" if ffmpeg_ok else "❌ Ошибка установки FFmpeg"
    await message.answer(status)

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку на видео")
        return
    
    await message.answer(
        "🎥 *Выберите качество:*\n\n"
        "• Для больших видео бот автоматически сожмёт их до 50 МБ\n"
        "• 360p-720p рекомендуются для быстрой загрузки",
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
        
        quality_names = {"144p":"144p","240p":"240p","360p":"360p","480p":"480p","720p":"720p","1080p":"1080p","best":"лучшее"}
        quality_name = quality_names.get(quality, quality)
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality_name}*...\nПожалуйста, подождите", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Не удалось скачать видео. Проверьте ссылку")
            await callback.answer()
            return
        
        await callback.message.edit_text(f"📤 Подготовка к отправке...")
        
        success = await send_file_auto(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await callback.message.delete()
            await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Не удалось скачать аудио")
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size > 50:
            await callback.message.answer_document(
                document=FSInputFile(file_path),
                caption=f"✅ *{title[:80]}*\n🎵 MP3 | {file_size:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.answer_audio(
                audio=FSInputFile(file_path),
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
    
    # Проверка FFmpeg
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, устанавливаю...")
        install_ffmpeg()
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
