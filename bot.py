import os
import asyncio
import subprocess
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН (ПОСЛЕ ОТЗЫВА СТАРОГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# 👇 Адрес ЛОКАЛЬНОГО Bot API сервера (ОБЯЗАТЕЛЬНО ДЛЯ БОЛЬШИХ ФАЙЛОВ)
# Инструкция по установке: https://core.telegram.org/bots/api#using-a-local-bot-api-server
LOCAL_BOT_API = "http://localhost:8081"  # Порт по умолчанию

# Папка для загрузок
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Настройки качества
QUALITY_FORMATS = {
    "144p": "worst[height<=144]",
    "240p": "best[height<=240]",
    "360p": "best[height<=360]",
    "480p": "best[height<=480]",
    "720p": "best[height<=720]",
    "1080p": "best[height<=1080]",
    "best": "best",
}

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

# ==================== FFMPEG АВТОУСТАНОВКА ====================
def auto_install_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("✅ FFmpeg уже установлен")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️ Устанавливаю FFmpeg...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'ffmpeg-setpath'])
            from ffmpeg_setpath import ffmpeg_setpath
            ffmpeg_setpath()
            print("✅ FFmpeg установлен!")
            return True
        except Exception as e:
            print(f"❌ Ошибка FFmpeg: {e}")
            return False

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
# Если LOCAL_BOT_API настроен, используем его для больших файлов
bot = Bot(token=BOT_TOKEN, base_url=LOCAL_BOT_API if LOCAL_BOT_API else None)
dp = Dispatcher()

# ==================== ФУНКЦИИ СКАЧИВАНИЯ ====================
def download_video_sync(url: str, quality: str):
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
            return filename, title
    except Exception as e:
        print(f"Ошибка: {e}")
        return None, None

def download_audio_sync(url: str):
    try:
        with YoutubeDL(AUDIO_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'audio')
            title = "".join(c for c in title if c not in r'\/:*?"<>|')
            
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp3') and title in f:
                    return os.path.join(DOWNLOAD_DIR, f), title
            return None, None
    except Exception as e:
        print(f"Ошибка аудио: {e}")
        return None, None

def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)

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

# ==================== ОБРАБОТЧИКИ ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот (Большие файлы до 2 ГБ)*\n\n"
        "✅ *Поддерживаются видео ЛЮБОГО размера* (до 2 ГБ)\n"
        "✅ Выбор качества: 144p → 1080p\n"
        "✅ Аудио в MP3\n\n"
        "📌 *Как работает:*\n"
        "1. Отправьте ссылку на видео\n"
        "2. Выберите качество\n"
        "3. Получите файл\n\n"
        "⚠️ Для работы с файлами >50 МБ нужен локальный Bot API сервер",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "🔹 *Лимиты:*\n"
        "• Обычный бот — 50 МБ\n"
        "• С локальным Bot API — ДО 2 ГБ\n\n"
        "🔹 *Как установить локальный Bot API:*\n"
        "1. https://core.telegram.org/bots/api#using-a-local-bot-api-server\n"
        "2. Запустите сервер на localhost:8081\n"
        "3. Раскомментируйте LOCAL_BOT_API в коде\n\n"
        "🔹 *Команды:*\n"
        "/start — Главное меню\n"
        "/help — Эта справка",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message()
async def handle_url(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("❌ Отправьте *ссылку* на видео", parse_mode=ParseMode.MARKDOWN)
        return
    
    keyboard = get_quality_keyboard(url)
    await message.answer(
        "🎥 *Выберите опцию:*\n\n"
        "• Видео с выбором качества\n"
        "• Аудио в MP3",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
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
        
        await callback.message.edit_text(f"⏳ Скачиваю *{quality}*...", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_video_sync, url, quality)
        
        if not file_path or not os.path.exists(file_path):
            await callback.message.edit_text("❌ Ошибка скачивания")
            await callback.answer()
            return
        
        file_size = get_file_size_mb(file_path)
        
        # Предупреждение о размере, но НЕ БЛОКИРУЕМ!
        size_warning = ""
        if file_size > 50:
            if not LOCAL_BOT_API:
                size_warning = f"\n\n⚠️ Файл {file_size:.1f} МБ > 50 МБ!\nУстановите локальный Bot API для отправки."
            else:
                size_warning = f"\n\n✅ Файл {file_size:.1f} МБ — отправляется через локальный API!"
        
        await callback.message.edit_text(f"📤 Отправляю {file_size:.1f} МБ...")
        
        try:
            video_file = FSInputFile(file_path)
            await bot.send_video(
                chat_id=callback.message.chat.id,
                video=video_file,
                caption=f"✅ *{title[:100]}*\n📹 {quality} | {file_size:.1f} МБ{size_warning}",
                supports_streaming=True,
                parse_mode=ParseMode.MARKDOWN
            )
            os.remove(file_path)
            await callback.message.delete()
            await callback.answer("✅ Готово!")
        except Exception as e:
            if "413" in str(e) or "Too Large" in str(e):
                await callback.message.edit_text(
                    f"❌ Файл {file_size:.1f} МБ превышает лимит 50 МБ!\n\n"
                    "🔧 *Решение:* Установите локальный Bot API сервер\n"
                    "https://core.telegram.org/bots/api#using-a-local-bot-api-server",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback.message.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            await callback.answer()
        
    elif action == "audio":
        url = parts[1]
        
        await callback.message.edit_text("⏳ Скачиваю аудио...", parse_mode=ParseMode.MARKDOWN)
        
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_audio_sync, url)
        
        if not file_path:
            await callback.message.edit_text("❌ Ошибка скачивания аудио")
            await callback.answer()
            return
        
        file_size = get_file_size_mb(file_path)
        await callback.message.edit_text(f"📤 Отправляю {file_size:.1f} МБ...")
        
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

# ==================== ЗАПУСК ====================
async def main():
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 50)
    
    auto_install_ffmpeg()
    
    print(f"📁 Папка: {os.path.abspath(DOWNLOAD_DIR)}")
    
    if LOCAL_BOT_API:
        print(f"✅ Локальный Bot API: {LOCAL_BOT_API}")
        print("✅ Файлы ДО 2 ГБ поддерживаются!")
    else:
        print("⚠️ Локальный Bot API НЕ настроен")
        print("⚠️ Лимит: 50 МБ")
        print("🔧 Настройте LOCAL_BOT_API для файлов >50 МБ")
    
    print("=" * 50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
