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
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН СЮДА (ПОСЛЕ ОТЗЫВА СТАРОГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI одним кодом м полностью "

# Папка для временного хранения файлов
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Словарь для временного хранения ссылок пользователей (пока они выбирают качество)
user_urls = {}

# Доступные форматы для скачивания
FORMATS = {
    'video_2160p': {'name': '🎬 4K (2160p)', 'format': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]', 'type': 'video'},
    'video_1080p': {'name': '🎬 Full HD (1080p)', 'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'type': 'video'},
    'video_720p': {'name': '🎬 HD (720p)', 'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'type': 'video'},
    'video_480p': {'name': '🎬 SD (480p)', 'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]', 'type': 'video'},
    'video_360p': {'name': '🎬 Низкое (360p)', 'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]', 'type': 'video'},
    'audio_mp3': {'name': '🎵 Аудио (MP3)', 'format': 'bestaudio/best', 'type': 'audio', 'extract_audio': True},
    'audio_m4a': {'name': '🎵 Аудио (M4A)', 'format': 'bestaudio/best', 'type': 'audio', 'extract_audio': True},
}

# ==================== АВТОУСТАНОВКА FFMPEG ====================
def auto_install_ffmpeg():
    """Автоматическая установка FFmpeg при первом запуске"""
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
    format_info = FORMATS.get(format_key, FORMATS['video_720p'])
    
    # Базовые настройки
    opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    
    # Настройки для видео
    if format_info['type'] == 'video':
        opts['format'] = format_info['format']
        opts['merge_output_format'] = 'mp4'
    # Настройки для аудио
    else:
        opts['format'] = format_info['format']
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3' if format_key == 'audio_mp3' else 'm4a',
            'preferredquality': '192',
        }]
    
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'media')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Получаем путь к скачанному файлу
            filename = ydl.prepare_filename(info)
            
            # Для аудио меняем расширение
            if format_info['type'] == 'audio':
                ext = 'mp3' if format_key == 'audio_mp3' else 'm4a'
                filename = filename.rsplit('.', 1)[0] + f'.{ext}'
            
            # Проверяем существование файла
            if not os.path.exists(filename):
                # Ищем любой недавний файл в папке
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

# ==================== КЛАВИАТУРА ДЛЯ ВЫБОРА КАЧЕСТВА ====================
def get_quality_keyboard():
    """Создает клавиатуру с кнопками выбора качества"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=FORMATS['video_2160p']['name'], callback_data="format_video_2160p"),
            InlineKeyboardButton(text=FORMATS['video_1080p']['name'], callback_data="format_video_1080p"),
        ],
        [
            InlineKeyboardButton(text=FORMATS['video_720p']['name'], callback_data="format_video_720p"),
            InlineKeyboardButton(text=FORMATS['video_480p']['name'], callback_data="format_video_480p"),
        ],
        [
            InlineKeyboardButton(text=FORMATS['video_360p']['name'], callback_data="format_video_360p"),
            InlineKeyboardButton(text=FORMATS['audio_mp3']['name'], callback_data="format_audio_mp3"),
        ],
        [
            InlineKeyboardButton(text=FORMATS['audio_m4a']['name'], callback_data="format_audio_m4a"),
        ],
    ])
    return keyboard

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте мне ссылку на видео, а затем выберите:\n"
        "• Качество видео (4K, 1080p, 720p, 480p, 360p)\n"
        "• Аудио (MP3 или M4A)\n\n"
        "⚠️ *Важно:* Telegram не позволяет отправлять файлы больше **2 ГБ**. "
        "Видео в 4K могут весить очень много и не отправятся.\n\n"
        "📖 /help — Помощь",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "1️⃣ Найдите видео на любом сайте\n"
        "2️⃣ Скопируйте ссылку\n"
        "3️⃣ Отправьте ссылку боту\n"
        "4️⃣ Выберите качество или аудио\n"
        "5️⃣ Дождитесь скачивания и отправки\n\n"
        "🎯 *Доступные форматы:*\n"
        "• 4K (2160p) — очень тяжелые файлы\n"
        "• 1080p — Full HD\n"
        "• 720p — HD (рекомендуется)\n"
        "• 480p — хорошее качество\n"
        "• 360p — экономия трафика\n"
        "• MP3 / M4A — только звук\n\n"
        "⚠️ *Лимит Telegram:* 2 ГБ на файл",
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
    
    # Сохраняем ссылку пользователя
    user_urls[message.from_user.id] = url
    
    # Показываем клавиатуру с выбором качества
    await message.answer(
        "🎯 *Выберите формат скачивания:*\n\n"
        "Видео в 4K могут весить более 2 ГБ и не отправятся в Telegram.\n"
        "Рекомендую 720p или 1080p для хорошего соотношения качества и размера.",
        reply_markup=get_quality_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== ОБРАБОТЧИК ВЫБОРА КАЧЕСТВА ====================
@dp.callback_query(lambda c: c.data.startswith('format_'))
async def process_format_selection(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    format_key = callback_query.data.replace('format_', '')
    
    # Проверяем, есть ли ссылка от этого пользователя
    if user_id not in user_urls:
        await callback_query.message.edit_text(
            "❌ Ссылка не найдена. Пожалуйста, отправьте ссылку заново."
        )
        await callback_query.answer()
        return
    
    url = user_urls[user_id]
    format_info = FORMATS.get(format_key, FORMATS['video_720p'])
    
    # Отвечаем на callback, чтобы убрать часики
    await callback_query.answer()
    
    # Обновляем сообщение, показывая, что началась загрузка
    await callback_query.message.edit_text(
        f"⏳ Начинаю скачивание...\n\n"
        f"📎 Формат: {format_info['name']}\n"
        f"🔗 Ссылка: {url[:50]}...\n\n"
        f"Это может занять некоторое время в зависимости от размера файла."
    )
    
    try:
        # Скачиваем в отдельном потоке
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_media_sync, url, format_key)
        
        if not file_path or not os.path.exists(file_path):
            await callback_query.message.edit_text(
                "❌ Не удалось скачать файл.\n\n"
                "Возможные причины:\n"
                "• Ссылка недействительна\n"
                "• Видео удалено или закрыто\n"
                "• Выбранный формат недоступен\n\n"
                "Попробуйте другой формат или ссылку."
            )
            # Удаляем сохраненную ссылку
            del user_urls[user_id]
            return
        
        # Проверяем размер файла (лимит Telegram 2 ГБ = 2048 МБ)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        file_size_gb = file_size_mb / 1024
        
        if file_size_mb > 2048:  # 2 ГБ лимит
            os.remove(file_path)
            await callback_query.message.edit_text(
                f"❌ Файл слишком большой ({file_size_gb:.2f} ГБ).\n"
                f"Telegram позволяет отправлять файлы не более **2 ГБ**.\n\n"
                f"Попробуйте выбрать более низкое качество или аудио."
            )
            del user_urls[user_id]
            return
        
        # Обновляем статус
        size_text = f"{file_size_gb:.2f} ГБ" if file_size_mb > 1024 else f"{file_size_mb:.1f} МБ"
        await callback_query.message.edit_text(
            f"📥 Скачивание завершено!\n\n"
            f"🎬 Название: {title[:50]}\n"
            f"📦 Размер: {size_text}\n"
            f"📎 Формат: {format_info['name']}\n\n"
            f"📤 Отправляю файл в Telegram..."
        )
        
        # Отправляем файл
        media_file = FSInputFile(file_path)
        
        if format_info['type'] == 'video':
            await bot.send_video(
                chat_id=callback_query.message.chat.id,
                video=media_file,
                caption=f"✅ *{title[:100]}*\n\n📎 {format_info['name']}\n📦 {size_text}",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Для аудио используем send_audio
            await bot.send_audio(
                chat_id=callback_query.message.chat.id,
                audio=media_file,
                caption=f"✅ *{title[:100]}*\n\n📎 {format_info['name']}\n📦 {size_text}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Удаляем временный файл и ссылку пользователя
        os.remove(file_path)
        del user_urls[user_id]
        
        # Удаляем сообщение со статусом
        await callback_query.message.delete()
        
    except Exception as e:
        print(f"Ошибка: {e}")
        await callback_query.message.edit_text(
            f"⚠️ Произошла ошибка:\n`{str(e)[:200]}`\n\n"
            f"Попробуйте другой формат или ссылку.",
            parse_mode=ParseMode.MARKDOWN
        )
        if user_id in user_urls:
            del user_urls[user_id]

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("=" * 50)
    print("🤖 Запуск бота...")
    print("=" * 50)
    
    # Автоматическая установка FFmpeg
    if not auto_install_ffmpeg():
        print("⚠️ Продолжаем без FFmpeg, но некоторые функции могут не работать")
    
    print(f"📁 Папка для загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Бот готов к работе!")
    print("🎯 Доступные форматы: 4K, 1080p, 720p, 480p, 360p, MP3, M4A")
    print("📨 Отправьте боту ссылку на видео...")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
