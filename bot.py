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
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Словарь с форматами качества
QUALITY_FORMATS = {
    "144p": "worst[height<=144]",
    "240p": "best[height<=240]",
    "360p": "best[height<=360]",
    "480p": "best[height<=480]",
    "720p": "best[height<=720]",
    "1080p": "best[height<=1080]",
    "best": "best",
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

# ==================== КЛАВИАТУРА ВЫБОРА ====================
def get_quality_keyboard(url: str):
    """Клавиатура для выбора качества видео"""
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

# ==================== ФУНКЦИИ СКАЧИВАНИЯ ====================
def download_video_sync(url: str, quality: str):
    """Скачивание видео с выбранным качеством"""
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
            
            # Поиск файла, если имя изменилось
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
                        return None, None
            
            return filename, title
            
    except Exception as e:
        print(f"Ошибка скачивания видео: {e}")
        return None, None

def download_audio_sync(url: str):
    """Скачивание только аудио в MP3"""
    try:
        with YoutubeDL(AUDIO_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            # Ищем mp3 файл
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp3') and title in f:
                    filename = os.path.join(DOWNLOAD_DIR, f)
                    return filename, title
            
            # Если не нашли по названию, берем самый свежий mp3
            files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) 
                    if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and f.endswith('.mp3')]
            if files:
                filename = max(files, key=os.path.getmtime)
                return filename, title
            
            return None, None
            
    except Exception as e:
        print(f"Ошибка скачивания аудио: {e}")
        return None, None

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Отправьте мне ссылку на видео, и я предложу:\n"
        "• Скачать в разном качестве (144p → 1080p)\n"
        "• Скачать только аудио (MP3)\n\n"
        "📖 /help — Подробнее",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите нужное качество или аудио\n"
        "3. Дождитесь загрузки\n\n"
        "⚠️ *Лимит Telegram:* 50 МБ\n"
        "• Видео 1080p часто превышают лимит\n"
        "• Рекомендую 720p или ниже\n"
        "• Аудио обычно влезает всегда\n\n"
        "🔧 Команды:\n"
        "/start — Начать\n"
        "/help — Помощь",
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
    
    # Показываем клавиатуру с выбором качества
    keyboard = get_quality_keyboard(url)
    await message.answer(
        "🎥 *Выберите опцию:*\n\n"
        "• Видео в разном качестве\n"
        "• Аудио в формате MP3",
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
    
    # Парсим данные (vid_720p_https://... или audio_https://...)
    parts = data.split("_", 2)
    if len(parts) < 2:
        await callback.answer("Ошибка формата")
        return
    
    action = parts[0]  # "vid" или "audio"
    
    if action == "vid":
        quality = parts[1]  # "144p", "240p", "360p", "480p", "720p", "1080p", "best"
        url = parts[2]
        
        await callback.message.edit_text(
            f"⏳ Скачиваю видео в качестве *{quality}*...\nЭто может занять некоторое время.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_video_sync, url, quality)
        
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
        
        # Проверка размера
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        if file_size > 50:
            os.remove(file_path)
            await callback.message.edit_text(
                f"❌ Видео слишком большое ({file_size:.1f} МБ).\n"
                f"Telegram лимит: 50 МБ.\n\n"
                f"Попробуйте качество ниже."
            )
            await callback.answer()
            return
        
        await callback.message.edit_text(f"📤 Отправляю видео... ({file_size:.1f} МБ)")
        
        video_file = FSInputFile(file_path)
        await bot.send_video(
            chat_id=callback.message.chat.id,
            video=video_file,
            caption=f"✅ *{title[:100]}*\n📹 Качество: {quality} | {file_size:.1f} МБ",
            supports_streaming=True,
            parse_mode=ParseMode.MARKDOWN
        )
        
        os.remove(file_path)
        await callback.message.delete()
        await callback.answer("✅ Готово!")
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text(
            "⏳ Скачиваю аудио в формате MP3...\nЭто может занять некоторое время.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text(
                "❌ Не удалось скачать аудио.\n\n"
                "Проверьте ссылку и попробуйте снова."
            )
            await callback.answer()
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        await callback.message.edit_text(f"📤 Отправляю аудио... ({file_size:.1f} МБ)")
        
        audio_file = FSInputFile(file_path)
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio_file,
            caption=f"✅ *{title[:100]}*\n🎵 MP3 | {file_size:.1f} МБ",
            parse_mode=ParseMode.MARKDOWN
        )
        
        os.remove(file_path)
        await callback.message.delete()
        await callback.answer("✅ Готово!")

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("=" * 50)
    print("🤖 Бот запущен!")
    print("=" * 50)
    
    auto_install_ffmpeg()
    
    print(f"📁 Папка загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Бот готов!")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
