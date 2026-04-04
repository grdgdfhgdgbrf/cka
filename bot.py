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
import ctypes
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА (ПОСЛЕ ОТЗЫВА СТАРОГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# ID администратора для получения логов (опционально)
ADMIN_ID = 5356400377

DOWNLOAD_DIR = "downloads"
CACHE_DIR = "cache"
CACHE_FILE = "video_cache.json"
LOG_FILE = "bot_log.txt"

for dir_name in [DOWNLOAD_DIR, CACHE_DIR]:
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

# ==================== ИСПРАВЛЕННАЯ УСТАНОВКА FFMPEG ====================
def add_to_system_path(path_to_add: str):
    """Добавление пути в системную переменную PATH"""
    try:
        # Получаем текущий PATH
        result = subprocess.run(['reg', 'query', 'HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment', '/v', 'Path'], 
                                capture_output=True, text=True)
        current_path = ""
        for line in result.stdout.split('\n'):
            if 'Path' in line and 'REG_' in line:
                current_path = line.split('    ')[-1].strip()
                break
        
        if path_to_add not in current_path:
            new_path = f"{current_path};{path_to_add}"
            # Обновляем системный PATH
            subprocess.run(f'setx /M PATH "{new_path}"', shell=True, capture_output=True)
            log_message(f"✅ PATH обновлён: добавлен {path_to_add}")
            
            # Обновляем PATH в текущем процессе
            os.environ['PATH'] = os.environ['PATH'] + os.pathsep + path_to_add
            return True
        return True
    except Exception as e:
        log_message(f"Ошибка обновления PATH: {e}", "ERROR")
        return False

def check_ffmpeg() -> bool:
    """Проверка наличия FFmpeg в системе"""
    try:
        # Проверяем в стандартных местах
        possible_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg.exe"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                log_message(f"✅ FFmpeg найден по пути: {path}")
                # Добавляем директорию в PATH если нужно
                bin_dir = os.path.dirname(path)
                if bin_dir not in os.environ['PATH']:
                    os.environ['PATH'] = os.environ['PATH'] + os.pathsep + bin_dir
                return True
        
        # Проверяем через команду
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_message("✅ FFmpeg работает через командную строку")
            return True
            
    except FileNotFoundError:
        pass
    except Exception as e:
        log_message(f"Ошибка проверки FFmpeg: {e}", "WARNING")
    
    log_message("❌ FFmpeg не найден")
    return False

def install_ffmpeg_windows():
    """Установка FFmpeg на Windows с автоматическим добавлением в PATH"""
    try:
        log_message("🚀 Начинаю установку FFmpeg на Windows...")
        
        # Скачиваем FFmpeg
        ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(os.getcwd(), "ffmpeg_temp.zip")
        extract_path = os.path.join(os.getcwd(), "ffmpeg_extract_temp")
        
        log_message(f"📥 Скачиваю FFmpeg с {ffmpeg_url}")
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        log_message("✅ Скачивание завершено")
        
        # Распаковываем
        log_message("📦 Распаковываю архив...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        log_message("✅ Распаковка завершена")
        
        # Находим папку bin с ffmpeg.exe
        bin_path = None
        for root, dirs, files in os.walk(extract_path):
            if 'ffmpeg.exe' in files:
                bin_path = root
                break
        
        if not bin_path:
            log_message("❌ Не найден ffmpeg.exe в архиве", "ERROR")
            return False
        
        log_message(f"📁 Найден FFmpeg в: {bin_path}")
        
        # Целевая папка
        target_path = r"C:\ffmpeg"
        target_bin_path = os.path.join(target_path, "bin")
        
        # Удаляем старую папку если есть
        if os.path.exists(target_path):
            log_message("🗑️ Удаляю старую версию FFmpeg...")
            shutil.rmtree(target_path, ignore_errors=True)
        
        # Создаём целевую папку и копируем
        os.makedirs(target_bin_path, exist_ok=True)
        
        # Копируем все файлы из bin
        for file in os.listdir(bin_path):
            src = os.path.join(bin_path, file)
            dst = os.path.join(target_bin_path, file)
            shutil.copy2(src, dst)
        
        log_message(f"✅ FFmpeg скопирован в {target_bin_path}")
        
        # Добавляем в PATH
        log_message("🔧 Добавляю FFmpeg в системный PATH...")
        if add_to_system_path(target_bin_path):
            log_message("✅ PATH обновлён успешно")
        else:
            log_message("⚠️ Не удалось обновить PATH автоматически", "WARNING")
        
        # Очистка временных файлов
        log_message("🧹 Очищаю временные файлы...")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)
        
        # Принудительно добавляем в текущий PATH
        os.environ['PATH'] = target_bin_path + os.pathsep + os.environ['PATH']
        
        # Проверяем установку
        log_message("🔍 Проверяю установку FFmpeg...")
        try:
            result = subprocess.run([os.path.join(target_bin_path, 'ffmpeg.exe'), '-version'], 
                                   capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                log_message("✅ FFmpeg успешно установлен и работает!")
                return True
            else:
                log_message(f"❌ FFmpeg не работает: {result.stderr}", "ERROR")
                return False
        except Exception as e:
            log_message(f"❌ Ошибка при проверке FFmpeg: {e}", "ERROR")
            return False
            
    except Exception as e:
        log_message(f"❌ Ошибка установки FFmpeg: {e}", "ERROR")
        log_message(traceback.format_exc(), "ERROR")
        return False

def auto_install_ffmpeg():
    """Автоматическая установка FFmpeg если не найден"""
    if check_ffmpeg():
        log_message("✅ FFmpeg уже установлен")
        return True
    
    log_message("⚠️ FFmpeg не найден, начинаю автоматическую установку...")
    
    if sys.platform == "win32":
        success = install_ffmpeg_windows()
    else:
        log_message("❌ Автоустановка только для Windows", "ERROR")
        success = False
    
    if success:
        log_message("✅ FFmpeg успешно установлен!")
        return check_ffmpeg()
    else:
        log_message("❌ Не удалось установить FFmpeg автоматически", "ERROR")
        return False

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ВИДЕО ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    unique_string = f"{url}_{quality}_{file_type}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def download_video_sync(url: str, quality: str):
    """Скачивание видео с кэшированием"""
    video_id = get_video_id(url, quality, "video")
    log_message(f"Скачивание видео: {url[:100]}, качество: {quality}")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Видео из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        format_str = QUALITY_FORMATS.get(quality, "best[height<=720]")
        
        opts = {
            'format': format_str,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',
        }
        
        with YoutubeDL(opts) as ydl:
            log_message("Получаю информацию о видео...")
            info = ydl.extract_info(url, download=True)
            
            if not info:
                log_message("❌ Не удалось получить информацию", "ERROR")
                return None, None, False
            
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            filename = ydl.prepare_filename(info)
            
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
                    else:
                        log_message("❌ Файл не найден", "ERROR")
                        return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Видео скачано: {title}, {file_size:.1f} МБ")
            
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
    audio_id = get_video_id(url, "mp3", "audio")
    log_message(f"Скачивание аудио: {url[:100]}")
    
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            log_message(f"✅ Аудио из кэша: {cached['title']}")
            return cached['path'], cached['title'], True
    
    try:
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
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
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and f.endswith('.mp3')]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    return None, None, False
            
            file_size = os.path.getsize(filename) / (1024 * 1024)
            log_message(f"✅ Аудио скачано: {title}, {file_size:.1f} МБ")
            
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
        log_message(f"❌ Ошибка: {e}", "ERROR")
        return None, None, False

# ==================== ОТПРАВКА ФАЙЛОВ ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    cache_text = " (из кэша ⚡)" if from_cache else ""
    
    try:
        if file_size_mb <= 50:
            video_file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            document_file = FSInputFile(file_path)
            await bot.send_document(
                chat_id=chat_id,
                document=document_file,
                caption=f"✅ *{title[:100]}*{cache_text}\n📹 {quality} | {file_size_mb:.1f} МБ\n⚠️ Видео >50 МБ, отправлено как файл",
                parse_mode=ParseMode.MARKDOWN
            )
        log_message(f"✅ Файл отправлен: {file_size_mb:.1f} МБ")
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
        [InlineKeyboardButton(text="🏆 Best", callback_data=f"vid_best_{url}"),
         InlineKeyboardButton(text="🎵 MP3", callback_data=f"audio_{url}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    return keyboard

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    log_message(f"Пользователь {message.from_user.id}: /start")
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте ссылку на видео.\n\n"
        "🔧 /check — Проверить FFmpeg\n"
        "🗑️ /clear_cache — Очистить кэш\n"
        "📊 /stats — Статистика\n"
        "📋 /log — Логи",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("check"))
async def check_command(message: types.Message):
    await message.answer("🔍 Проверяю FFmpeg...")
    if check_ffmpeg():
        await message.answer("✅ FFmpeg установлен и работает!")
    else:
        await message.answer("⚠️ FFmpeg не найден, устанавливаю...")
        success = auto_install_ffmpeg()
        if success:
            await message.answer("✅ FFmpeg успешно установлен!")
        else:
            await message.answer("❌ Не удалось установить FFmpeg. Смотри /log")

@dp.message(Command("log"))
async def log_command(message: types.Message):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-30:]
            await message.answer(f"📋 *Логи:*\n```\n{''.join(last_lines)[:3000]}\n```", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Лог-файл не найден.")

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
    global video_cache
    deleted = 0
    for info in video_cache.values():
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
                deleted += 1
            except:
                pass
    video_cache = {}
    save_cache(video_cache)
    await message.answer(f"🗑️ Очищено {deleted} файлов")

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_size = 0
    for info in video_cache.values():
        if os.path.exists(info['path']):
            total_size += os.path.getsize(info['path'])
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"📁 В кэше: {len(video_cache)}\n"
        f"💾 Занято: {total_size/(1024*1024):.1f} МБ\n"
        f"⚡ FFmpeg: {'✅' if check_ffmpeg() else '❌'}",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИКИ ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    log_message(f"Ссылка от {message.from_user.id}: {url[:100]}")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте ссылку (http:// или https://)")
        return
    
    await message.answer("🎥 *Выберите качество:*", reply_markup=get_quality_keyboard(url), parse_mode=ParseMode.MARKDOWN)

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
        quality_name = QUALITY_NAMES.get(quality, quality)
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality_name}*...\nЛоги в /log", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания.\nСмотри /log")
            await callback.answer()
            return
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality_name, from_cache)
        await callback.message.delete()
        await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...")
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания аудио")
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*\n🎵 MP3 | {file_size:.1f} МБ" + (" ⚡(кэш)" if from_cache else ""),
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"📄 Логи: {LOG_FILE}")
    print("-" * 60)
    
    # Автоустановка FFmpeg
    if not check_ffmpeg():
        print("⚠️ FFmpeg не найден, устанавливаю...")
        auto_install_ffmpeg()
    else:
        print("✅ FFmpeg уже установлен")
    
    print("=" * 60)
    print("✅ Бот готов!")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
