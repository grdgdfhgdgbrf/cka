import os
import asyncio
import subprocess
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# Папка для временного хранения файлов
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Хранилище выбора пользователя (в реальном проекте лучше использовать БД)
user_choices = {}

# Базовые настройки для yt-dlp
BASE_YDL_OPTS = {
    'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
}

# Доступные форматы
FORMATS = {
    '2160p': {'format': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]', 'merge': 'mp4', 'name': '4K (2160p)'},
    '1440p': {'format': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]', 'merge': 'mp4', 'name': '2K (1440p)'},
    '1080p': {'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'merge': 'mp4', 'name': 'Full HD (1080p)'},
    '720p':  {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'merge': 'mp4', 'name': 'HD (720p)'},
    '480p':  {'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]', 'merge': 'mp4', 'name': 'SD (480p)'},
    '360p':  {'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]', 'merge': 'mp4', 'name': '360p'},
    'audio': {'format': 'bestaudio/best', 'merge': None, 'name': '🎵 Аудио (MP3)', 'extract_audio': True}
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

# ==================== ФУНКЦИЯ СКАЧИВАНИЯ ====================
def download_media_sync(url: str, format_key: str):
    """Скачивает видео или аудио в зависимости от выбранного формата"""
    try:
        format_config = FORMATS[format_key]
        
        # Настраиваем параметры
        opts = BASE_YDL_OPTS.copy()
        opts['format'] = format_config['format']
        
        if format_config['merge']:
            opts['merge_output_format'] = format_config['merge']
        
        if format_key == 'audio':
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            opts['outtmpl'] = f'{DOWNLOAD_DIR}/%(title)s.%(ext)s'
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'media')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Определяем путь к файлу
            if format_key == 'audio':
                filename = f"{DOWNLOAD_DIR}/{title}.mp3"
                if not os.path.exists(filename):
                    # Ищем любой mp3 файл
                    for f in os.listdir(DOWNLOAD_DIR):
                        if f.endswith('.mp3') and title in f:
                            filename = os.path.join(DOWNLOAD_DIR, f)
                            break
            else:
                filename = ydl.prepare_filename(info)
                if not os.path.exists(filename):
                    for f in os.listdir(DOWNLOAD_DIR):
                        if f.endswith('.mp4') and title in f:
                            filename = os.path.join(DOWNLOAD_DIR, f)
                            break
            
            if not os.path.exists(filename):
                # Берем самый свежий файл
                files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                if files:
                    filename = max(files, key=os.path.getmtime)
                else:
                    return None, None
            
            return filename, title
            
    except Exception as e:
        print(f"Ошибка в yt-dlp: {e}")
        return None, None

# ==================== КЛАВИАТУРЫ ====================
def get_quality_keyboard(url: str):
    """Создает клавиатуру с выбором качества"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 4K (2160p)", callback_data=f"quality_2160p|{url}")],
        [InlineKeyboardButton(text="🎬 2K (1440p)", callback_data=f"quality_1440p|{url}")],
        [InlineKeyboardButton(text="🎬 Full HD (1080p)", callback_data=f"quality_1080p|{url}")],
        [InlineKeyboardButton(text="🎬 HD (720p)", callback_data=f"quality_720p|{url}")],
        [InlineKeyboardButton(text="🎬 SD (480p)", callback_data=f"quality_480p|{url}")],
        [InlineKeyboardButton(text="🎬 360p", callback_data=f"quality_360p|{url}")],
        [InlineKeyboardButton(text="🎵 Аудио (MP3)", callback_data=f"quality_audio|{url}")],
    ])
    return keyboard

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот с выбором качества*\n\n"
        "📌 *Как пользоваться:*\n"
        "1. Отправьте мне ссылку на видео\n"
        "2. Выберите нужное качество или аудио\n"
        "3. Получите файл!\n\n"
        "✨ *Особенности:*\n"
        "• Поддержка 4K, 2K, 1080p, 720p и ниже\n"
        "• Конвертация в MP3\n"
        "• Автоматическая установка FFmpeg\n\n"
        "📖 /help — Подробная справка",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Подробная инструкция*\n\n"
        "1️⃣ *Отправьте ссылку*\n"
        "Скопируйте ссылку на видео из браузера и отправьте боту\n\n"
        "2️⃣ *Выберите формат*\n"
        "Бот покажет кнопки с разными качествами:\n"
        "• 4K/2K/1080p — для больших экранов\n"
        "• 720p/480p — оптимальный размер\n"
        "• Аудио — только звук в MP3\n\n"
        "3️⃣ *Получите файл*\n"
        "Бот скачает и отправит файл\n\n"
        "⚠️ *Ограничения:*\n"
        "• Telegram НЕ позволяет отправлять файлы >50 МБ\n"
        "• Для 4K/2K видео могут превышать лимит\n"
        "• В этом случае выберите качество ниже\n\n"
        "🔧 *Команды:*\n"
        "/start — Главное меню\n"
        "/help — Эта справка",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК ССЫЛОК ====================
@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            "❌ Пожалуйста, отправьте *ссылку* на видео.\n\n"
            "Ссылка должна начинаться с http:// или https://",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Показываем клавиатуру с выбором качества
    await message.answer(
        "📥 *Ссылка получена!*\n\n"
        "Выберите качество или аудио формат:",
        reply_markup=get_quality_keyboard(url),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК ВЫБОРА КАЧЕСТВА ====================
@dp.callback_query()
async def handle_quality_selection(callback: CallbackQuery):
    if not callback.data.startswith("quality_"):
        return
    
    # Разбираем данные
    _, format_key, url = callback.data.split("|", 2)
    
    # Отвечаем на callback, чтобы убрать "часики"
    await callback.answer(f"Выбран формат: {FORMATS[format_key]['name']}")
    
    # Редактируем сообщение, показываем статус
    await callback.message.edit_text(
        f"🔄 *Выбран:* {FORMATS[format_key]['name']}\n\n"
        f"⏳ Начинаю загрузку...\n"
        f"📍 URL: {url[:50]}...\n\n"
        f"_Это может занять некоторое время..._",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Скачиваем файл в отдельном потоке
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_media_sync, url, format_key)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text(
                "❌ *Не удалось скачать файл*\n\n"
                "Возможные причины:\n"
                "• Ссылка недействительна\n"
                "• Выбранное качество недоступно\n"
                "• Видео требует авторизации\n\n"
                "Попробуйте другой формат или видео.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Проверяем размер файла
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size > 50:
            os.remove(file_path)
            await callback.message.edit_text(
                f"⚠️ *Файл слишком большой!*\n\n"
                f"Размер: {file_size:.1f} МБ\n"
                f"Лимит Telegram: 50 МБ\n\n"
                f"Попробуйте выбрать качество ниже или аудио формат.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Обновляем статус
        await callback.message.edit_text(
            f"✅ *Загрузка завершена!*\n\n"
            f"📹 Название: {title[:60]}\n"
            f"📊 Размер: {file_size:.1f} МБ\n"
            f"🎬 Формат: {FORMATS[format_key]['name']}\n\n"
            f"📤 Отправляю файл...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Отправляем файл
        media_file = FSInputFile(file_path)
        
        if format_key == 'audio':
            await bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=media_file,
                caption=f"🎵 *{title[:100]}*",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=media_file,
                caption=f"🎬 *{title[:100]}*\n🎚️ {FORMATS[format_key]['name']}",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Удаляем временный файл
        os.remove(file_path)
        
        # Финальное сообщение
        await callback.message.edit_text(
            f"✅ *Готово!*\n\n"
            f"Видео успешно отправлено!\n"
            f"📹 {FORMATS[format_key]['name']}\n\n"
            f"🔗 [Открыть в Telegram](https://t.me/{callback.from_user.username})",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Ошибка: {e}")
        await callback.message.edit_text(
            f"⚠️ *Произошла ошибка*\n\n"
            f"```\n{str(e)[:200]}\n```\n\n"
            f"Попробуйте другой формат или повторите позже.",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("=" * 50)
    print("🤖 Бот с выбором качества запускается...")
    print("=" * 50)
    
    # Автоматическая установка FFmpeg
    if not auto_install_ffmpeg():
        print("⚠️ Продолжаем без FFmpeg, но некоторые функции могут не работать")
    
    print(f"📁 Папка для загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Доступные форматы:")
    for key, fmt in FORMATS.items():
        print(f"   • {fmt['name']}")
    print("=" * 50)
    print("✅ Бот готов к работе!")
    print("📨 Отправьте боту ссылку на видео...")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
