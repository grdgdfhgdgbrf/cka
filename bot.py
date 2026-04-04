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
import re
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
    if os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe"):
        os.environ['PATH'] = r"C:\ffmpeg\bin" + os.pathsep + os.environ.get('PATH', '')
        log_message("✅ FFmpeg найден в C:\\ffmpeg\\bin")
        return True
    
    # Проверяем в текущей папке
    if os.path.exists("ffmpeg.exe"):
        os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ.get('PATH', '')
        log_message("✅ FFmpeg найден в текущей папке")
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
                    # Копируем в текущую папку
                    for file in os.listdir(bin_path):
                        src = os.path.join(bin_path, file)
                        dst = os.path.join(os.getcwd(), file)
                        shutil.copy2(src, dst)
                    # Удаляем временную папку
                    shutil.rmtree(item, ignore_errors=True)
                    break
        
        os.remove(zip_path)
        
        # Добавляем в PATH
        os.environ['PATH'] = os.getcwd() + os.pathsep + os.environ.get('PATH', '')
        
        log_message("✅ FFmpeg установлен")
        return True
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

# ==================== СЖАТИЕ ВИДЕО ====================
def compress_video(input_path: str, output_path: str, target_size_mb: int = 45):
    """Сжатие видео до целевого размера"""
    try:
        # Получаем длительность видео
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path],
            capture_output=True, text=True, timeout=30
        )
        duration = float(result.stdout.strip())
        
        # Рассчитываем битрейт (в бит/с)
        # (target_size_mb * 8 * 1024 * 1024) / duration
        bitrate = int((target_size_mb * 8 * 1024 * 1024) / duration)
        # Ограничиваем битрейт
        bitrate = min(bitrate, 2000000)  # Максимум 2 Mbps
        bitrate = max(bitrate, 500000)    # Минимум 0.5 Mbps
        
        log_message(f"Сжатие: длительность={duration}s, битрейт={bitrate} bps")
        
        # Сжимаем видео
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',
            '-b:v', str(bitrate),
            '-c:a', 'aac',
            '-b:a', '128k',
            '-preset', 'fast',
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            log_message(f"✅ Сжато: {new_size:.1f} МБ (было {os.path.getsize(input_path)/(1024*1024):.1f} МБ)")
            return output_path
        else:
            log_message(f"Ошибка сжатия: {result.stderr}", "ERROR")
            return None
            
    except Exception as e:
        log_message(f"Ошибка сжатия: {e}", "ERROR")
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
    
    log_message(f"Скачивание: {url} | {quality}")
    
    try:
        # Форматы качества
        if quality == "144p":
            format_spec = 'worst[height<=144]'
        elif quality == "240p":
            format_spec = 'best[height<=240]'
        elif quality == "360p":
            format_spec = 'best[height<=360]'
        elif quality == "480p":
            format_spec = 'best[height<=480]'
        elif quality == "720p":
            format_spec = 'best[height<=720]'
        elif quality == "1080p":
            format_spec = 'best[height<=1080]'
        else:
            format_spec = 'best'
        
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
            
            if not filename:
                return None, None, False
            
            file_size_mb = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Скачано: {title}, {file_size_mb:.1f} МБ")
            
            # Если видео больше 50 МБ, пробуем сжать
            if file_size_mb > 50:
                log_message(f"Видео {file_size_mb:.1f} МБ > 50 МБ, пробую сжать...")
                compressed_path = os.path.join(DOWNLOAD_DIR, f"compressed_{os.path.basename(filename)}")
                compressed = compress_video(filename, compressed_path, 45)
                if compressed and os.path.exists(compressed):
                    # Заменяем оригинал сжатым
                    os.remove(filename)
                    filename = compressed
                    new_size = os.path.getsize(filename) / (1024 * 1024)
                    log_message(f"✅ После сжатия: {new_size:.1f} МБ")
            
            video_cache[video_id] = {
                'path': filename,
                'title': title,
                'quality': quality,
                'url': url,
                'date': datetime.now().isoformat(),
                'size_mb': os.path.getsize(filename) / (1024 * 1024)
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
            
            if not filename:
                return None, None, False
            
            video_cache[audio_id] = {
                'path': filename,
                'title': title,
                'type': 'audio',
                'url': url,
                'date': datetime.now().isoformat(),
                'size_mb': os.path.getsize(filename) / (1024 * 1024)
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        log_message(f"Ошибка: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА (С ПОДДЕРЖКОЙ ФАЙЛОВ >50 МБ) ====================
async def send_file_auto(message, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " ⚡(из кэша)" if from_cache else ""
    
    try:
        # Если файл больше 50 МБ - отправляем как документ (до 2 ГБ)
        if file_size_mb > 50:
            log_message(f"Файл {file_size_mb:.1f} МБ > 50 МБ, отправляю как документ")
            doc_file = FSInputFile(file_path)
            await message.answer_document(
                document=doc_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n\n⚠️ *Видео превышает 50 МБ*, поэтому отправлено как файл. Скачайте его, чтобы посмотреть.",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Файл отправлен как документ ({file_size_mb:.1f} МБ)")
        else:
            # Маленькое видео - отправляем как видео с плеером
            video_file = FSInputFile(file_path)
            await message.answer_video(
                video=video_file,
                caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message(f"✅ Видео отправлено ({file_size_mb:.1f} МБ)")
        return True
        
    except Exception as e:
        log_message(f"Ошибка отправки: {e}", "ERROR")
        
        # Если ошибка "Request Entity Too Large", пробуем отправить как документ
        if "Request Entity Too Large" in str(e):
            try:
                log_message("Повторная отправка как документ...")
                doc_file = FSInputFile(file_path)
                await message.answer_document(
                    document=doc_file,
                    caption=f"✅ *{title[:80]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                    parse_mode=ParseMode.MARKDOWN
                )
                return True
            except:
                pass
        
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
        "Отправьте ссылку на видео с YouTube, Instagram, TikTok и других сайтов.\n\n"
        "⚡ *Особенности:*\n"
        "• Кэширование - повторные видео приходят мгновенно\n"
        "• Автоустановка FFmpeg\n"
        "• Поддержка файлов до 2 ГБ (отправка как документа)\n"
        "• Автоматическое сжатие видео >50 МБ\n\n"
        "📋 /log — Показать логи\n"
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
            await message.answer(f"📋 *Последние логи:*\n```\n{log_text[:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
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
        f"💾 Занято места: {total_size/(1024*1024):.1f} МБ\n"
        f"✅ FFmpeg: {'Установлен' if check_ffmpeg() else 'Не установлен'}",
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
    await message.answer(f"🗑️ Очищено {deleted} файлов из кэша")

@dp.message(Command("check"))
async def check_cmd(message: types.Message):
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        await message.answer("⚠️ FFmpeg не найден, устанавливаю...")
        install_ffmpeg()
        ffmpeg_ok = check_ffmpeg()
    
    status = "✅ *Система готова*" if ffmpeg_ok else "❌ *Ошибка установки FFmpeg*"
    await message.answer(f"{status}\n\nFFmpeg: {'✅' if ffmpeg_ok else '❌'}", parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку, начинающуюся с http:// или https://")
        return
    
    await message.answer(
        "🎥 *Выберите опцию:*\n\n"
        "• 144p-720p - оптимально для Telegram\n"
        "• 1080p/Best - может быть большой вес\n"
        "• MP3 - только звук\n\n"
        "💡 *Совет:* Если видео не отправляется из-за веса, бот автоматически отправит его как файл (до 2 ГБ)",
        reply_markup=get_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    log_message(f"Callback: {data[:100]}")
    
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
            error_msg = "❌ Не удалось скачать видео.\n\nПроверьте ссылку и попробуйте другое качество."
            await callback.message.edit_text(error_msg)
            await callback.answer("Ошибка")
            return
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size_mb > 50:
            await callback.message.edit_text(f"📤 Видео весит {file_size_mb:.1f} МБ (>50 МБ)\nОтправляю как файл для скачивания...")
        else:
            await callback.message.edit_text(f"📤 Отправляю видео ({file_size_mb:.1f} МБ)...")
        
        success = await send_file_auto(callback.message, file_path, title, quality_name, from_cache)
        
        if success:
            await callback.message.delete()
            await callback.answer("✅ Готово!" if not from_cache else "⚡ Из кэша!")
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
        cache_text = " ⚡(из кэша)" if from_cache else ""
        
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
            await callback.message.edit_text(f"❌ Ошибка отправки: {str(e)[:100]}")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 50)
    
    # Проверка и установка FFmpeg
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, устанавливаю...")
        install_ffmpeg()
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📄 Логи: {LOG_FILE}")
    print("=" * 50)
    print("✅ Бот готов к работе!")
    print("💡 Видео >50 МБ отправляются как файлы (до 2 ГБ)")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
