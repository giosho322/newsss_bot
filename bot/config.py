import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Список Telegram каналов для мониторинга
TELEGRAM_CHANNELS = [
    "https://t.me/tproger",  # Примеры реальных IT каналов
    "https://t.me/habr", 
    # Добавьте сюда нужные вам каналы
]

NEWS_SOURCES = {
    "habr": "https://habr.com/ru/rss/all/",
    "tproger": "https://tproger.ru/feed/",
    "vc": "https://vc.ru/feed"
}