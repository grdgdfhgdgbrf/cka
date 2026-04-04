import os
import asyncio
import subprocess
import sys
import json
import hashlib
import traceback
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА (ПОСЛЕ ОТЗЫВА СТАРОГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# ID администратора для получения логов (можно оставить None)
ADMIN_ID = None  # Вставьте ваш Telegram ID, например: 123456789

DOWNLOAD_DIR = "downloads"
CACHE_DIR = "cache"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

for dir_name in [DOWNLOAD_DIR, CACHE_DIR]:
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

# ==================== ЛОГИРОВАНИЕ ====================
def log_message(msg: str, level: str = "INFO"):
    """Запись лога в файл и вывод в консоль"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {msg}"
    print(log_entry)
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

async def send_log_to_admin(text: str):
    """Отправка лога администратору"""
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"📋 *Лог бота:*\n`{text[:3000]}`", parse_mode=ParseMode.MARKDOWN)
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
log_message(f"Загружено {len(video_cache)} записей кэша")

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

# ==================== УЛУЧШЕННАЯ АВТОУСТАНОВКА FFMPEG ====================
def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg в системе"""
    try:
        # Проверяем через where/which
        if sys.platform == "win32":
            result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True)
        else:
            result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        
        if result.returncode == 0:
            log_message(f"✅ FFmpeg найден: {result.stdout.strip()}")
            return True
        
        # Прямая проверка
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_message("✅ FFmpeg работает")
            return True
    except FileNotFoundError:
        pass
    
    log_message("❌ FFmpeg не найден", "WARNING")
    return False

def install_ffmpeg_windows():
    """Установка FFmpeg на Windows"""
    try:
        log_message("Начинаю установку FFmpeg на Windows...")
        
        # Скачиваем FFmpeg
        import urllib.request
        import zipfile
        
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg.zip")
        extract_path = os.path.join(os.getcwd(), "ffmpeg_temp")
        
        log_message(f"Скачиваю FFmpeg с {ffmpeg_url}")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        # Распаковываем
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # Находим папку bin
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        # Копируем в Program Files
        target_path = r"C:\ffmpeg"
        if not os.path.exists(target_path):
            shutil.copytree(bin_path, target_path)
        
        # Добавляем в PATH
        subprocess.run(f'setx PATH "%PATH%;{target_path}" /M', shell=True)
        
        # Очистка
        os.remove(zip_path)
        shutil.rmtree(extract_path)
        
        log_message("✅ FFmpeg успешно установлен!")
        return True
        
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def install_ffmpeg_linux():
    """Установка FFmpeg на Linux"""
    try:
        log_message("Устанавливаю FFmpeg на Linux...")
        subprocess.run(['sudo', 'apt', 'update'], check=True)
        subprocess.run(['sudo', 'apt', 'install', '-y', 'ffmpeg'], check=True)
        log_message("✅ FFmpeg успешно установлен!")
        return True
    except Exception as e:
        log_message(f"Ошибка установки FFmpeg: {e}", "ERROR")
        return False

def auto_install_ffmpeg():
    """Автоматическая установка FFmpeg"""
    if check_ffmpeg():
        return True
    
    log_message("FFmpeg не найден, начинаю автоматическую установку...")
    
    if sys.platform == "win32":
        success = install_ffmpeg_windows()
    else:
        success = install_ffmpeg_linux()
    
    if success:
        # Проверяем после установки
        os.environ['PATH'] = os.environ['PATH'] + os.pathsep + r"C:\ffmpeg"
        return check_ffmpeg()
    
    return False

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ВИДЕО ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    """Генерация уникального ID"""
    unique_string = f"{url}_{quality}_{file_type}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def test_url_accessible(url: str) -> tuple:
    """Проверка доступности URL"""
    try:
        import requests
        response = requests.head(url, timeout=10, allow_redirects=True)
        log_message(f"Проверка URL {url}: статус {response.status_code}")
        return response.status_code < 400, response.status_code
    except Exception as e:
        log_message(f"Ошибка проверки URL: {e}", "WARNING")
        return True, None  # Предполагаем, что доступно

def download_video_sync(url: str, quality: str):
    """Скачивание видео с кэшированием и подробным логированием"""
    video_id = get_video_id(url, quality, "video")
    log_message(f"Начинаю скачивание видео: {url}, качество: {quality}")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Видео найдено в кэше: {cached['title']}")
            return cached['path'], cached['title'], True
    
    # Проверяем FFmpeg
    if not check_ffmpeg():
        log_message("❌ FFmpeg не установлен, скачивание может не работать", "ERROR")
    
    try:
        format_str = QUALITY_FORMATS.get(quality, "best[height<=720]")
        
        opts = {
            'format': format_str,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
            'quiet': False,  # Включаем вывод для логов
            'no_warnings': False,
            'merge_output_format': 'mp4',
            'verbose': True,  # Подробные логи
        }
        
        log_message(f"Параметры yt-dlp: {opts}")
        
        with YoutubeDL(opts) as ydl:
            # Получаем информацию
            log_message("Получаю информацию о видео...")
            info = ydl.extract_info(url, download=False)
            
            if not info:
                log_message("❌ Не удалось получить информацию о видео", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            log_message(f"Видео найдено: {title}, длительность: {duration} сек")
            
            # Скачиваем
            log_message("Начинаю скачивание...")
            info = ydl.extract_info(url, download=True)
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            filename = ydl.prepare_filename(info)
            
            log_message(f"Ожидаемый файл: {filename}")
            
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
                        log_message(f"Найден альтернативный файл: {filename}")
                    else:
                        log_message("❌ Файл не найден после скачивания", "ERROR")
                        return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Видео скачано: {filename}, размер: {file_size:.1f} МБ")
            
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
        log_message(f"❌ Ошибка скачивания видео: {e}", "ERROR")
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио с логированием"""
    audio_id = get_video_id(url, "mp3", "audio")
    log_message(f"Начинаю скачивание аудио: {url}")
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Аудио найдено в кэше: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        with YoutubeDL(opts) as ydl:
            log_message("Получаю информацию об аудио...")
            info = ydl.extract_info(url, download=True)
            
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Ищем mp3 файл
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
                    log_message("❌ MP3 файл не найден", "ERROR")
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Аудио скачано: {filename}, размер: {file_size:.1f} МБ")
            
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
        log_message(f"❌ Ошибка скачивания аудио: {e}", "ERROR")
        log_message(traceback.format_exc(), "ERROR")
        return None, None, False

# ==================== ФУНКЦИЯ ОТПРАВКИ ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    """Отправка файла с логированием"""
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT_VIDEO = 50
    
    cache_text = " (из кэша ⚡)" if from_cache else ""
    log_message(f"Отправляю файл: {file_path}, размер: {file_size_mb:.1f} МБ, из кэша: {from_cache}")
    
    try:
        if file_size_mb <= LIMIT_VIDEO:
            video_file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 Качество: {quality} | {file_size_mb:.1f} МБ",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
            log_message("✅ Видео отправлено (send_video)")
        else:
            document_file = FSInputFile(file_path)
            await bot.send_document(
                chat_id=chat_id,
                document=document_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n"
                        f"📹 Качество: {quality} | {file_size_mb:.1f} МБ\n\n"
                        f"⚠️ *Видео превышает 50 МБ*, отправлено как файл.",
                parse_mode=ParseMode.MARKDOWN
            )
            log_message("✅ Видео отправлено (send_document)")
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
        [InlineKeyboardButton(text="🏆 Best Quality", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    return keyboard

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    log_message(f"Пользователь {message.from_user.id} запустил бота")
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте мне ссылку на видео.\n\n"
        "📋 /log — Показать последние логи\n"
        "🗑️ /clear_cache — Очистить кэш\n"
        "📊 /stats — Статистика\n"
        "🔧 /check_ffmpeg — Проверить FFmpeg",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("log"))
async def log_command(message: types.Message):
    """Отправка логов пользователю"""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:]  # Последние 30 строк
            log_text = "".join(last_lines)
            await message.answer(f"📋 *Последние логи:*\n```\n{log_text[:3000]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Лог-файл не найден.")

@dp.message(Command("check_ffmpeg"))
async def check_ffmpeg_command(message: types.Message):
    """Проверка FFmpeg"""
    if check_ffmpeg():
        await message.answer("✅ FFmpeg установлен и работает!")
    else:
        await message.answer("❌ FFmpeg НЕ установлен. Бот пытается установить автоматически...")
        success = auto_install_ffmpeg()
        if success:
            await message.answer("✅ FFmpeg успешно установлен!")
        else:
            await message.answer("❌ Не удалось установить FFmpeg автоматически. Установите вручную.")

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
    global video_cache
    deleted_count = 0
    
    for video_id, info in video_cache.items():
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
                deleted_count += 1
            except:
                pass
    
    video_cache = {}
    save_cache(video_cache)
    
    log_message(f"Кэш очищен, удалено {deleted_count} файлов")
    await message.answer(f"🗑️ *Кэш очищен!*\nУдалено файлов: {deleted_count}", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_size = 0
    for video_id, info in video_cache.items():
        if os.path.exists(info['path']):
            total_size += os.path.getsize(info['path'])
    
    size_mb = total_size / (1024 * 1024)
    
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {size_mb:.1f} МБ\n"
        f"⚡ FFmpeg: {'✅' if check_ffmpeg() else '❌'}",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК ССЫЛОК ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Получено сообщение от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте *ссылку* на видео.", parse_mode=ParseMode.MARKDOWN)
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
    log_message(f"Callback от {callback.from_user.id}: {data[:100]}")
    
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
            f"⏳ Скачиваю *{quality_name}*...\nЛоги в /log",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            error_msg = "❌ Не удалось скачать видео.\n\nПроверьте /log для деталей."
            await callback.message.edit_text(error_msg)
            await send_log_to_admin(f"Ошибка скачивания: {url}\n{quality}")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality_name, from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!" if not from_cache else "⚡ Из кэша!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text("❌ Не удалось скачать аудио.\nПроверьте /log")
            await callback.answer()
            return
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*\n🎵 MP3 | {file_size_mb:.1f} МБ" + (" ⚡(кэш)" if from_cache else ""),
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📄 Файл логов: {LOG_FILE}")
    print(f"💾 Кэш: {len(video_cache)} записей")
    print("-" * 60)
    
    # Проверяем FFmpeg
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, пытаюсь установить...")
        auto_install_ffmpeg()
    
    print("✅ Бот готов к работе!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
