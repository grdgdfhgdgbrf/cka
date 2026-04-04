import os
import asyncio
import subprocess
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.enums import ParseMode
from yt_dlp import YoutubeDL

# ==================== КОНФИГУРАЦИЯ ====================
# 👇 ВСТАВЬТЕ ВАШ ТОКЕН СЮДА (НЕ ПУБЛИКУЙТЕ ЕГО!)
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# Папка для временного хранения файлов
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Настройки для yt-dlp
YDL_OPTS = {
    'format': 'best[height<=720]',
    'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'merge_output_format': 'mp4',
}

# ==================== АВТОУСТАНОВКА FFMPEG ====================
def auto_install_ffmpeg():
    """
    Автоматическая установка FFmpeg через библиотеку ffmpeg-setpath
    Запускается при первом запуске бота
    """
    try:
        # Проверяем, установлен ли FFmpeg
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg уже установлен")
            return True
    except FileNotFoundError:
        print("⚠️ FFmpeg не найден, начинаю автоматическую установку...")
    
    try:
        # Устанавливаем библиотеку для автоустановки
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'ffmpeg-setpath'])
        
        # Импортируем и запускаем установку
        from ffmpeg_setpath import ffmpeg_setpath
        ffmpeg_setpath()
        
        print("✅ FFmpeg успешно установлен!")
        
        # Добавляем небольшую задержку, чтобы система обновила PATH
        import time
        time.sleep(2)
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при установке FFmpeg: {e}")
        print("Попробуйте установить FFmpeg вручную по инструкции выше.")
        return False

# ==================== ФУНКЦИЯ СКАЧИВАНИЯ ====================
def download_video_sync(url: str):
    """Синхронная функция для скачивания видео"""
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
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
                            if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                    if files:
                        filename = max(files, key=os.path.getmtime)
                    else:
                        return None, None
            
            return filename, title
            
    except Exception as e:
        print(f"Ошибка в yt-dlp: {e}")
        return None, None

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "🎬 *Видео-Бот*\n\n"
        "Просто отправьте мне ссылку на видео с:\n"
        "• YouTube\n"
        "• Instagram (Reels, видео в посте)\n"
        "• TikTok\n"
        "• Twitter / X\n"
        "• VK\n"
        "• Facebook\n\n"
        "Я скачаю его и отправлю вам файлом! 📥\n\n"
        "📖 /help — Помощь",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "1. Найдите видео на любом сайте\n"
        "2. Скопируйте ссылку из адресной строки\n"
        "3. Вставьте ссылку сюда и отправьте\n"
        "4. Дождитесь загрузки и скачивания\n\n"
        "⚠️ *Важно:* Telegram не позволяет отправлять файлы больше 50 МБ.\n\n"
        "🔧 Команды:\n"
        "/start — Приветствие\n"
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
    
    status_msg = await message.answer("🔄 Получаю информацию о видео...")
    
    try:
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_video_sync, url)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ Не удалось скачать видео.\n\n"
                "Возможные причины:\n"
                "• Ссылка недействительна\n"
                "• Видео удалено или закрыто\n"
                "• Сайт требует авторизации\n\n"
                "Попробуйте другую ссылку."
            )
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        if file_size > 500:
            os.remove(file_path)
            await status_msg.edit_text(
                f"❌ Видео слишком большое ({file_size:.1f} МБ).\n"
                "Telegram позволяет отправлять не более 50 МБ."
            )
            return
        
        await status_msg.edit_text(f"📥 Скачивание завершено! Отправляю видео...\n\n🎬 {title[:50]}")
        
        video_file = FSInputFile(file_path)
        await bot.send_video(
            chat_id=message.chat.id,
            video=video_file,
            caption=f"✅ *{title[:100]}*",
            supports_streaming=True,
            parse_mode=ParseMode.MARKDOWN
        )
        
        os.remove(file_path)
        await status_msg.delete()
        
    except Exception as e:
        print(f"Ошибка: {e}")
        await status_msg.edit_text(
            f"⚠️ Произошла ошибка:\n`{str(e)[:200]}`",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("=" * 50)
    print("🤖 Запуск бота...")
    print("=" * 50)
    
    # Автоматическая установка FFmpeg при первом запуске
    if not auto_install_ffmpeg():
        print("⚠️ Продолжаем без FFmpeg, но некоторые видео могут не скачаться")
    
    print(f"📁 Папка для загрузок: {os.path.abspath(DOWNLOAD_DIR)}")
    print("✅ Бот готов к работе!")
    print("📨 Отправьте боту ссылку на видео...")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
