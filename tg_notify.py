import asyncio
import logging
from datetime import datetime
import os

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

# --- КОНФИГУРАЦИЯ ---
# Данные будут браться из "Environment Variables" на хостинге

# 1. Токен вашего телеграм-бота
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# 2. ID вашего чата или канала
# Мы преобразуем его в число, так как переменные окружения - это всегда текст
TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID"))

# 3. Ваши ключи от Twitch
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")

# 4. Список никнеймов стримеров на Twitch для отслеживания
# Мы получаем строку "nick1,nick2,nick3" и превращаем ее в список
TWITCH_CHANNELS = [name.strip() for name in os.environ.get("TWITCH_CHANNELS").split(',')]

# --- Конец конфигурации ---


# --- Функции для работы с Twitch API ---

async def get_twitch_token():
    """Получает или обновляет токен доступа для Twitch API."""
    global twitch_access_token
    url = f"https://id.twitch.tv/oauth2/token?client_id={TWITCH_CLIENT_ID}&client_secret={TWITCH_CLIENT_SECRET}&grant_type=client_credentials"
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as response:
            if response.status == 200:
                data = await response.json()
                twitch_access_token = data['access_token']
                logging.info("Токен доступа Twitch успешно получен.")
            else:
                logging.error(f"Ошибка получения токена Twitch: {response.status} - {await response.text()}")
                twitch_access_token = None

async def check_twitch_streams():
    """Проверяет статусы стримов на Twitch."""
    if not twitch_access_token:
        logging.warning("Нет токена доступа Twitch. Пропускаю проверку.")
        await get_twitch_token() # Пробуем получить токен снова
        if not twitch_access_token:
            return

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {twitch_access_token}",
    }
    
    user_logins = "&".join([f"user_login={name}" for name in TWITCH_CHANNELS])
    url = f"https://api.twitch.tv/helix/streams?{user_logins}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    current_online = {stream['user_login'].lower(): stream for stream in data.get('data', [])}
                    
                    for channel_login, stream_data in current_online.items():
                        if channel_login not in online_streams:
                            logging.info(f"{channel_login} вышел в онлайн!")
                            online_streams[channel_login] = stream_data['id']
                            await send_notification(stream_data)

                    for channel_login in list(online_streams.keys()):
                        if channel_login not in current_online:
                            logging.info(f"{channel_login} закончил стрим.")
                            del online_streams[channel_login]

                elif response.status == 401:
                    logging.warning("Токен Twitch недействителен. Запрашиваю новый.")
                    await get_twitch_token()
                else:
                    logging.error(f"Ошибка при запросе к Twitch API: {response.status} - {await response.text()}")
    except Exception as e:
        logging.error(f"Произошла ошибка при проверке стримов: {e}")

async def send_notification(stream_data):
    """Формирует и отправляет уведомление в Telegram."""
    user_name = stream_data.get('user_name')
    title = stream_data.get('title')
    game_name = stream_data.get('game_name', 'N/A')
    thumbnail_url = stream_data.get('thumbnail_url').replace('{width}', '1280').replace('{height}', '720')
    
    thumbnail_url_with_ts = f"{thumbnail_url}?timestamp={int(datetime.now().timestamp())}"

    message_text = (
        f"🔴 **{user_name} в эфире!**\n\n"
        f"**Стрим:** {title}\n"
        f"**Игра:** {game_name}\n\n"
        f"https://www.twitch.tv/{stream_data.get('user_login')}"
    )

    try:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=thumbnail_url_with_ts,
            caption=message_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление для {user_name}: {e}")


# --- Основной цикл и запуск ---

async def scheduler():
    """Планировщик, который запускает проверку каждые 60 секунд."""
    while True:
        await check_twitch_streams()
        await asyncio.sleep(60)

@dp.message(CommandStart())
async def send_welcome(message: Message):
    await message.reply("Привет! Я бот для уведомлений о стримах. Я буду присылать оповещения в настроенный канал.")

async def main():
    # Получаем токен при запуске
    await get_twitch_token()
    # Запускаем планировщик в фоновом режиме
    asyncio.create_task(scheduler())
    # Запускаем обработку сообщений
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())