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
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА (ПОСЛЕ ОТЗЫВА СТАРОГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

DOWNLOAD_DIR = "downloads"
CACHE_DIR = "cache"
CACHE_FILE = "video_cache.json"

for dir_name in [DOWNLOAD_DIR, CACHE_DIR]:
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

# Настройки для аудио
AUDIO_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# ==================== АВТОУСТАНОВКА FFMPEG ====================
def auto_install_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg уже установлен")
            return True
    except FileNotFoundError:
        print("⚠️ FFmpeg не найден, начинаю автоматическую установку...")
    
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'ffmpeg-setpath'])
        from ffmpeg_setpath import ffmpeg_setpath
        ffmpeg_setpath()
        print("✅ FFmpeg успешно установлен!")
        import time
        time.sleep(2)
        return True
    except Exception as e:
        print(f"❌ Ошибка при установке FFmpeg: {e}")
        return False

# ==================== ГЕНЕРАЦИЯ УНИКАЛЬНОГО ID ВИДЕО ====================
def get_video_id(url: str, quality: str, file_type: str = "video") -> str:
    """Генерирует уникальный ID для видео на основе URL, качества и типа"""
    unique_string = f"{url}_{quality}_{file_type}"
    return hashlib.md5(unique_string.encode()).hexdigest()

# ==================== КЛАВИАТУРА ВЫБОРА ====================
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

# ==================== ФУНКЦИИ СКАЧИВАНИЯ С КЭШИРОВАНИЕМ ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео с кэшированием"""
    video_id = get_video_id(url, quality, "video")
    
    # Проверяем кэш
    if video_id in video_cache:
        cached = video_cache[video_id]
        if os.path.exists(cached['path']):
            print(f"✅ Видео найдено в кэше: {cached['title']}")
            return cached['path'], cached['title'], True  # True = из кэша
    
    try:
        format_str = QUALITY_FORMATS.get(quality, "best[height<=720]")
        
        opts = {
            'format': format_str,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(height)sp.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            filename = ydl.prepare_filename(info)
            
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
        print(f"Ошибка скачивания видео: {e}")
        return None, None, False

def download_audio_sync(url: str):
    """Скачивание аудио с кэшированием"""
    audio_id = get_video_id(url, "mp3", "audio")
    
    # Проверяем кэш
    if audio_id in video_cache:
        cached = video_cache[audio_id]
        if os.path.exists(cached['path']):
            print(f"✅ Аудио найдено в кэше: {cached['title']}")
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
            
            # Сохраняем в кэш
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
        print(f"Ошибка скачивания аудио: {e}")
        return None, None, False

# ==================== ФУНКЦИЯ ОТПРАВКИ С ОБХОДОМ ЛИМИТА ====================
async def send_file_auto(chat_id: int, file_path: str, title: str, quality: str, from_cache: bool = False):
    """Автоматически выбирает метод отправки в зависимости от размера файла"""
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    LIMIT_VIDEO = 50
    
    cache_text = " (из кэша ⚡)" if from_cache else ""
    
    if file_size_mb <= LIMIT_VIDEO:
        video_file = FSInputFile(file_path)
        await bot.send_video(
            chat_id=chat_id,
            video=video_file,
            caption=f"✅ *{title[:100]}*{cache_text}\n📹 Качество: {quality} | {file_size_mb:.1f} МБ",
            supports_streaming=True,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        document_file = FSInputFile(file_path)
        await bot.send_document(
            chat_id=chat_id,
            document=document_file,
            caption=f"✅ *{title[:100]}*{cache_text}\n"
                    f"📹 Качество: {quality} | {file_size_mb:.1f} МБ\n\n"
                    f"⚠️ *Видео превышает 50 МБ*, отправлено как файл.\n"
                    f"📥 Скачайте файл, чтобы посмотреть видео.",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот (с кэшированием!)*\n\n"
        "⚡ *Особенности:*\n"
        "• Видео сохраняются в кэш\n"
        "• При повторном запросе — *мгновенная отправка*\n"
        "• Без повторного скачивания!\n\n"
        "Отправьте мне ссылку на видео, и я предложу:\n"
        "• Скачать в разном качестве (144p → 1080p)\n"
        "• Скачать только аудио (MP3)\n\n"
        "📖 /help — Подробнее\n"
        "🗑️ /clear_cache — Очистить кэш",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите нужное качество или аудио\n"
        "3. Дождитесь загрузки (первый раз)\n"
        "4. При повторной отправке — *видео придёт мгновенно!*\n\n"
        "📦 *Лимиты:*\n"
        "• Видео до 50 МБ → с плеером\n"
        "• Видео 50+ МБ → файл для скачивания\n"
        "• Аудио → всегда с плеером\n\n"
        "⚡ *Кэш:*\n"
        "• Все скачанные видео сохраняются\n"
        "• Повторная отправка занимает 1-2 секунды\n"
        "• Команда /clear_cache — очистить кэш\n\n"
        "🔧 Команды:\n"
        "/start — Начать\n"
        "/help — Помощь\n"
        "/clear_cache — Очистить кэш\n"
        "/stats — Статистика кэша",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("clear_cache"))
async def clear_cache_command(message: types.Message):
    """Очистка кэша"""
    global video_cache
    deleted_count = 0
    
    # Удаляем физические файлы
    for video_id, info in video_cache.items():
        if os.path.exists(info['path']):
            try:
                os.remove(info['path'])
                deleted_count += 1
            except:
                pass
    
    # Очищаем кэш
    video_cache = {}
    save_cache(video_cache)
    
    await message.answer(
        f"🗑️ *Кэш очищен!*\n\n"
        f"Удалено файлов: {deleted_count}\n"
        f"Освобождено место на диске.",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    """Статистика кэша"""
    total_size = 0
    for video_id, info in video_cache.items():
        if os.path.exists(info['path']):
            total_size += os.path.getsize(info['path'])
    
    size_mb = total_size / (1024 * 1024)
    
    await message.answer(
        f"📊 *Статистика кэша*\n\n"
        f"📁 Видео в кэше: {len(video_cache)}\n"
        f"💾 Занято места: {size_mb:.1f} МБ ({size_mb/1024:.2f} ГБ)\n\n"
        f"⚡ *Преимущество:*\n"
        f"Повторные запросы этих видео будут\n"
        f"отправлены мгновенно без скачивания!",
        parse_mode=ParseMode.MARKDOWN
    )

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
        "🎥 *Выберите опцию:*\n\n"
        "• Видео в разном качестве\n"
        "• Аудио в формате MP3\n\n"
        "⚡ *Если видео уже скачивали раньше* — оно придёт мгновенно!",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК КНОПОК ====================
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    data = callback.data
    
    if data == "cancel":
        await callback.message.edit_text("❌ Операция отменена.")
        await callback.answer()
        return
    
    parts = data.split("_", 2)
    if len(parts) < 2:
        await callback.answer("Ошибка формата")
        return
    
    action = parts[0]
    
    if action == "vid":
        quality = parts[1]
        url = parts[2]
        quality_name = QUALITY_NAMES.get(quality, quality)
        
        # Проверяем, есть ли видео в кэше
        video_id = get_video_id(url, quality, "video")
        is_cached = video_id in video_cache and os.path.exists(video_cache[video_id]['path'])
        
        if is_cached:
            await callback.message.edit_text(
                f"⚡ *Видео найдено в кэше!*\n"
                f"Отправляю мгновенно без скачивания...\n\n"
                f"📹 Качество: {quality_name}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.edit_text(
                f"⏳ Скачиваю видео в качестве *{quality_name}*...\n"
                f"Это может занять некоторое время.\n\n"
                f"💡 *При повторном запросе видео придёт мгновенно!*",
                parse_mode=ParseMode.MARKDOWN
            )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text(
                "❌ Не удалось скачать видео.\n\n"
                "Возможные причины:\n"
                "• Ссылка недействительна\n"
                "• Выбранное качество недоступно\n"
                "• Видео требует авторизации"
            )
            await callback.answer()
            return
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size_mb > 50:
            await callback.message.edit_text(
                f"📤 Видео весит *{file_size_mb:.1f} МБ* (больше 50 МБ).\n"
                f"Отправляю как файл для скачивания...",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            if from_cache:
                await callback.message.edit_text(f"⚡ Отправляю видео из кэша...")
            else:
                await callback.message.edit_text(f"📤 Отправляю видео... ({file_size_mb:.1f} МБ)")
        
        await send_file_auto(callback.message.chat.id, file_path, title, quality_name, from_cache)
        
        # Не удаляем файл, он остается в кэше!
        await callback.message.delete()
        await callback.answer("✅ Готово!" if not from_cache else "⚡ Отправлено из кэша!")
        
    elif action == "audio":
        url = parts[1]
        
        # Проверяем кэш аудио
        audio_id = get_video_id(url, "mp3", "audio")
        is_cached = audio_id in video_cache and os.path.exists(video_cache[audio_id]['path'])
        
        if is_cached:
            await callback.message.edit_text(
                f"⚡ *Аудио найдено в кэше!*\n"
                f"Отправляю мгновенно...",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.message.edit_text(
                "⏳ Скачиваю аудио в формате MP3...\n"
                "Это может занять некоторое время.\n\n"
                "💡 *При повторном запросе аудио придёт мгновенно!*",
                parse_mode=ParseMode.MARKDOWN
            )
        
        loop = asyncio.get_event_loop()
        file_path, title, from_cache = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text(
                "❌ Не удалось скачать аудио.\n\n"
                "Проверьте ссылку и попробуйте снова."
            )
            await callback.answer()
            return
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if from_cache:
            await callback.message.edit_text(f"⚡ Отправляю аудио из кэша...")
        else:
            await callback.message.edit_text(f"📤 Отправляю аудио... ({file_size_mb:.1f} МБ)")
        
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*\n🎵 MP3 | {file_size_mb:.1f} МБ" + (" ⚡(из кэша)" if from_cache else ""),
            parse_mode=ParseMode.MARKDOWN
        )
        
        await callback.message.delete()
        await callback.answer("✅ Готово!" if not from_cache else "⚡ Отправлено из кэша!")

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("=" * 50)
    print("🤖 Бот запущен!")
    print("⚡ Включено кэширование видео!")
    print(f"📦 Видео в кэше: {len(video_cache)}")
    print("=" * 50)
    
    auto_install_ffmpeg()
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"💾 Файл кэша: {CACHE_FILE}")
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
