import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yt_dlp import YoutubeDL

# ==================================================
#  НАСТРОЙКИ - ИЗМЕНИТЕ ЭТО ПОД СЕБЯ
# ==================================================

# 1. ВСТАВЬТЕ СВОЙ ТОКЕН ОТ @BotFather
BOT_TOKEN = "7827714466:AAHzDGe1vXLkFksfxmIHNO67SOxfDsgJVtI"

# 2. Настройки качества видео (измените при желании)
#    Доступные опции:
#    'best' - самое лучшее качество (может быть >50 МБ)
#    'best[height<=720]' - не выше 720p (рекомендую)
#    'best[height<=480]' - не выше 480p (для медленного интернета)
#    'worst' - самое низкое качество
QUALITY = 'best[height<=720]'

# 3. Папка для временного хранения (не меняйте, если не нужно)
DOWNLOAD_DIR = "downloads"

# ==================================================
#  КОД БОТА - НИЖЕ НИЧЕГО НЕ МЕНЯЙТЕ
# ==================================================

# Создаём папку для скачанных видео
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Настройки для yt-dlp
YDL_OPTS = {
    'format': QUALITY,
    'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'merge_output_format': 'mp4',
    # Раскомментируйте следующую строку, если у вас есть файл cookies.txt
    # 'cookiefile': 'cookies.txt',
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def download_video_sync(url: str):
    """
    Синхронная функция скачивания видео.
    Возвращает (путь_к_файлу, название_видео) или (None, None) при ошибке
    """
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            # Скачиваем видео и получаем информацию
            info = ydl.extract_info(url, download=True)
            
            # Получаем имя файла
            filename = ydl.prepare_filename(info)
            
            # Если файла нет (было слияние потоков), ищем .mp4
            if not os.path.exists(filename):
                base = filename.rsplit('.', 1)[0]
                if os.path.exists(base + '.mp4'):
                    filename = base + '.mp4'
                elif os.path.exists(base + '.webm'):
                    filename = base + '.webm'
            
            # Если всё равно не нашли, ищем самый свежий файл в папке
            if not os.path.exists(filename):
                files = [f for f in os.listdir(DOWNLOAD_DIR) 
                        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
                if files:
                    files.sort(key=lambda x: os.path.getmtime(
                        os.path.join(DOWNLOAD_DIR, x)), reverse=True)
                    filename = os.path.join(DOWNLOAD_DIR, files[0])
            
            title = info.get('title', 'video')
            # Убираем недопустимые символы из названия
            title = ''.join(c for c in title if c.isprintable() and c not in '/\\:*?"<>|')
            
            return filename, title
            
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None, None


@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Приветственное сообщение"""
    await message.answer(
        "🎬 **Видео-Бот**\n\n"
        "Просто отправьте мне ссылку на видео, и я скачаю его!\n\n"
        "**Поддерживаются:**\n"
        "• YouTube, YouTube Shorts\n"
        "• Instagram Reels, IGTV\n"
        "• TikTok\n"
        "• Twitter/X\n"
        "• Reddit\n"
        "• VK (ВКонтакте)\n"
        "• И ещё 1000+ сайтов\n\n"
        f"📦 **Качество:** {QUALITY}\n"
        "⚠️ **Лимит Telegram:** 50 МБ\n\n"
        "Просто отправь ссылку → получишь видео",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Справка"""
    await message.answer(
        "📖 **Как пользоваться:**\n\n"
        "1. Найди видео на любом сайте\n"
        "2. Скопируй ссылку из адресной строки\n"
        "3. Отправь ссылку мне\n"
        "4. Дождись скачивания и отправки\n\n"
        "⚠️ Если видео больше 50 МБ, я не смогу его отправить в Telegram.\n\n"
        "**Команды:**\n"
        "/start - Приветствие\n"
        "/help - Эта справка\n"
        "/quality - Изменить качество",
        parse_mode="Markdown"
    )


@dp.message(Command("quality"))
async def quality_command(message: types.Message):
    """Показать текущее качество и инструкцию по смене"""
    await message.answer(
        f"🎯 **Текущее качество:** `{QUALITY}`\n\n"
        "Изменить качество можно в файле `bot.py` в строке `QUALITY = ...`\n\n"
        "**Доступные варианты:**\n"
        "• `best` - максимальное\n"
        "• `best[height<=1080]` - Full HD (1080p)\n"
        "• `best[height<=720]` - HD (720p)\n"
        "• `best[height<=480]` - SD (480p)\n"
        "• `worst` - минимальное",
        parse_mode="Markdown"
    )


@dp.message()
async def handle_url(message: types.Message):
    """Обработка ссылок"""
    url = message.text.strip()
    
    # Проверяем, является ли сообщение ссылкой
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer(
            "❌ Это не похоже на ссылку.\n"
            "Отправьте ссылку, начинающуюся с http:// или https://"
        )
        return
    
    # Отправляем статус
    status_msg = await message.answer("⏳ Получаю информацию о видео...")
    
    try:
        # Запускаем скачивание в отдельном потоке
        loop = asyncio.get_event_loop()
        file_path, title = await loop.run_in_executor(None, download_video_sync, url)
        
        # Проверяем, скачалось ли
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ Не удалось скачать видео.\n\n"
                "Возможные причины:\n"
                "• Видео защищено (приватное/18+)\n"
                "• Ссылка недействительна\n"
                "• Сайт требует авторизации\n"
                "• Видео слишком большое"
            )
            return
        
        # Получаем размер файла
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # в МБ
        
        # Если файл больше 50 МБ, предупреждаем
        if file_size > 50:
            await status_msg.edit_text(
                f"⚠️ Видео весит {file_size:.1f} МБ, что больше лимита Telegram (50 МБ).\n\n"
                "Попробуйте:\n"
                "• Выбрать качество пониже (команда /quality)\n"
                "• Скачать в формате аудио (в разработке)"
            )
            # Всё равно пытаемся отправить, но вероятнее всего не получится
            # Telegram вернёт ошибку, если файл >50 МБ
        
        # Обновляем статус
        await status_msg.edit_text("📤 Видео скачано! Отправляю...")
        
        # Отправляем видео
        video_file = FSInputFile(file_path)
        
        # Обрезаем слишком длинное название для подписи
        caption = f"✅ **{title[:60]}**"
        if len(title) > 60:
            caption += "..."
        
        try:
            await bot.send_video(
                chat_id=message.chat.id,
                video=video_file,
                caption=caption,
                supports_streaming=True,
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as send_error:
            if "file is too big" in str(send_error).lower():
                await status_msg.edit_text(
                    "❌ Видео слишком большое для Telegram (максимум 50 МБ).\n\n"
                    "Используйте команду /quality, чтобы выбрать более низкое качество."
                )
            else:
                await status_msg.edit_text(f"❌ Ошибка при отправке: {str(send_error)[:100]}")
        
        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass
        
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        await status_msg.edit_text(
            f"❌ Произошла ошибка:\n{str(e)[:150]}\n\n"
            "Попробуйте другую ссылку или позже."
        )


async def main():
    """Запуск бота"""
    print("=" * 50)
    print("🤖 Бот для скачивания видео запущен!")
    print(f"📁 Папка для скачивания: {DOWNLOAD_DIR}")
    print(f"🎯 Качество видео: {QUALITY}")
    print("=" * 50)
    print("Бот готов к работе. Нажми Ctrl+C для остановки.")
    print("=" * 50)
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
