import os
import asyncio
import subprocess
import sys
import json
import hashlib
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"  # ЗАМЕНИТЕ ПОСЛЕ ОТЗЫВА СТАРОГО!

# Получаем абсолютный путь к папке проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
CACHE_FILE = os.path.join(BASE_DIR, "video_cache.json")

for dir_name in [DOWNLOAD_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# Загрузка кэша
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

video_cache = load_cache()

# Форматы качества
QUALITY_FORMATS = {
    "144p": "worst[height<=144]",
    "240p": "best[height<=240]",
    "360p": "best[height<=360]",
    "480p": "best[height<=480]",
    "720p": "best[height<=720]",
    "1080p": "best[height<=1080]",
    "best": "best",
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

AUDIO_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
    'quiet': False,
    'no_warnings': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# ==================== ПРОВЕРКА FFMPEG ====================
def check_ffmpeg():
    """Проверяет доступность FFmpeg в системе"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg найден")
            return True
    except FileNotFoundError:
        pass
    
    # Проверяем в папке проекта
    ffmpeg_paths = [
        os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(BASE_DIR, "ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]
    
    for path in ffmpeg_paths:
        if os.path.exists(path):
            print(f"✅ FFmpeg найден по пути: {path}")
            return True
    
    print("❌ FFmpeg НЕ НАЙДЕН!")
    print("Установите FFmpeg вручную:")
    print("1. Скачайте с https://www.gyan.dev/ffmpeg/builds/")
    print("2. Распакуйте в C:\\ffmpeg")
    print("3. Добавьте C:\\ffmpeg\\bin в PATH")
    return False

# ==================== ФУНКЦИИ СКАЧИВАНИЯ ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    unique_string = f"{url}_{quality}_{file_type}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def download_video_sync(url: str, quality: str):
    """Скачивание видео с диагностикой"""
    video_id = get_video_id(url, quality, "video")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            print(f"✅ Видео в кэше: {cached['path']}")
            return cached['path'], cached['title'], True
    
    try:
        format_str = QUALITY_FORMATS.get(quality, "best[height<=720]")
        
        opts = {
            'format': format_str,
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s_%(height)sp.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',
            'verbose': True,  # Включаем подробный лог для отладки
        }
        
        print(f"📥 Начинаю скачивание: {url}")
        print(f"📁 Папка загрузок: {DOWNLOAD_DIR}")
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            filename = ydl.prepare_filename(info)
            
            print(f"📄 Ожидаемый файл: {filename}")
            
            # Проверяем существование файла
            if os.path.exists(filename):
                print(f"✅ Файл найден: {filename}")
            else:
                # Ищем любой mp4 файл
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and f.endswith('.mp4')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                    print(f"📄 Найден альтернативный файл: {filename}")
                else:
                    print("❌ Файл не найден после скачивания!")
                    return None, None, False
            
            # Сохраняем в кэш
            video_cache[video_id] = {
                'path': filename,
                'title': title,
                'quality': quality,
                'url': url,
                'date': datetime.now().isoformat()
            }
            save_cache(video_cache)
            
            return filename, title, False
            
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио"""
    audio_id = get_video_id(url, "mp3", "audio")
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            return cached['path'], cached['title'], True
    
    try:
        with YoutubeDL(AUDIO_OPTS) as ydl:
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
        print(f"❌ Ошибка скачивания аудио: {e}")
        return None, None, False

# ==================== ФУНКЦИЯ ОТПРАВКИ (ИСПРАВЛЕНА) ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    """
    Отправка файла с использованием правильных путей
    """
    # Получаем абсолютный путь
    abs_path = os.path.abspath(file_path)
    
    # ПРОВЕРЯЕМ СУЩЕСТВОВАНИЕ ФАЙЛА
    if not os.path.exists(abs_path):
        print(f"❌ Файл не найден: {abs_path}")
        return False
    
    file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    print(f"📤 Отправка файла: {abs_path}")
    print(f"📊 Размер: {file_size_mb:.1f} МБ")
    
    cache_text = " ⚡(из кэша)" if from_cache else ""
    
    try:
        # ИСПРАВЛЕНО: Используем FileInput с правильным путём
        video_file = FSInputFile(abs_path)
        
        if file_size_mb <= 50:
            # Отправляем как видео
            await bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 Качество: {quality} | {file_size_mb:.1f} МБ",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Отправляем как документ
            await bot.send_document(
                chat_id=chat_id,
                document=video_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n"
                        f"📹 Качество: {quality} | {file_size_mb:.1f} МБ\n\n"
                        f"⚠️ Видео превышает 50 МБ, отправлено как файл.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        print(f"✅ Файл успешно отправлен!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        
        # Пробуем альтернативный метод - через bytes
        try:
            print("🔄 Пробую альтернативный метод отправки...")
            with open(abs_path, 'rb') as f:
                file_bytes = f.read()
            
            await bot.send_document(
                chat_id=chat_id,
                document=types.BufferedInputFile(file_bytes, filename=os.path.basename(abs_path)),
                caption=f"✅ *{title[:100]}*{cache_text}\n(отправлено через BufferedInputFile)",
                parse_mode=ParseMode.MARKDOWN
            )
            print(f"✅ Альтернативный метод сработал!")
            return True
        except Exception as e2:
            print(f"❌ Альтернативный метод тоже не сработал: {e2}")
            return False

# ==================== КЛАВИАТУРА ====================
def get_quality_keyboard(url: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 144p", callback_data=f"vid_144p_{url}"),
         InlineKeyboardButton(text="🎬 240p", callback_data=f"vid_240p_{url}"),
         InlineKeyboardButton(text="🎬 360p", callback_data=f"vid_360p_{url}")],
        [InlineKeyboardButton(text="🎬 480p", callback_data=f"vid_480p_{url}"),
         InlineKeyboardButton(text="🎬 720p", callback_data=f"vid_720p_{url}"),
         InlineKeyboardButton(text="🎬 1080p", callback_data=f"vid_1080p_{url}")],
        [InlineKeyboardButton(text="🏆 Best Quality", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    return keyboard

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте мне ссылку на видео.\n\n"
        "📌 *Совет:* Если видео не отправляется, попробуйте качество ниже.\n\n"
        "📖 /help — Помощь",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите качество\n"
        "3. Дождитесь загрузки\n\n"
        "🔧 /stats — Статистика\n"
        "🗑️ /clear_cache — Очистить кэш",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_size = 0
    for video_id, info in video_cache.items():
        if os.path.exists(info.get('path', '')):
            total_size += os.path.getsize(info['path'])
    
    size_mb = total_size / (1024 * 1024)
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 Файлов в кэше: {len(video_cache)}\n"
        f"💾 Занято места: {size_mb:.1f} МБ\n"
        f"📂 Папка: `{DOWNLOAD_DIR}`",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
    global video_cache
    deleted = 0
    
    for video_id, info in video_cache.items():
        if os.path.exists(info.get('path', '')):
            try:
                os.remove(info['path'])
                deleted += 1
            except:
                pass
    
    video_cache = {}
    save_cache(video_cache)
    
    await message.answer(f"🗑️ Очищено! Удалено файлов: {deleted}")

# ==================== ОБРАБОТЧИК ССЫЛОК ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            "❌ Отправьте *ссылку* на видео.\n\n"
            "Ссылка должна начинаться с http:// или https://",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    keyboard = get_quality_keyboard(url)
    await message.answer(
        "🎥 *Выберите опцию:*",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК КНОПОК ====================
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    if data == "cancel":
        await callback.message.edit_text("❌ Отменено.")
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
        
        await callback.message.edit_text(
            f"⏳ Скачиваю *{quality_name}*...\n"
            f"Это может занять некоторое время.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text(
                "❌ *Не удалось скачать видео*\n\n"
                "Возможные причины:\n"
                "• Ссылка недействительна\n"
                "• Выбранное качество недоступно\n"
                "• Нет подключения к интернету\n\n"
                "Попробуйте другую ссылку или качество.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        
        await callback.message.edit_text(f"📤 Отправляю видео...")
        
        success = await send_file_auto(callback.message.chat.id, file_path, title, quality_name, from_cache)
        
        if success:
            await callback.message.delete()
            await callback.answer("✅ Готово!")
        else:
            await callback.message.edit_text(
                "❌ *Не удалось отправить видео*\n\n"
                "Возможные причины:\n"
                "• Файл повреждён\n"
                "• Проблемы с сервером Telegram\n\n"
                "Попробуйте скачать заново.",
                parse_mode=ParseMode.MARKDOWN
            )
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text("❌ Не удалось скачать аудио.")
            await callback.answer()
            return
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        cache_text = " ⚡(из кэша)" if from_cache else ""
        
        audio_file = FSInputFile(os.path.abspath(file_path))
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*{cache_text}\n🎵 MP3 | {file_size_mb:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 50)
    print("🤖 Бот запущен!")
    print(f"📁 Папка: {BASE_DIR}")
    print(f"📂 Downloads: {DOWNLOAD_DIR}")
    print("=" * 50)
    
    # Проверяем FFmpeg
    check_ffmpeg()
    
    print(f"📦 Видео в кэше: {len(video_cache)}")
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
