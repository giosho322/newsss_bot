import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Список Telegram каналов для мониторинга
TELEGRAM_CHANNELS = [
    "https://t.me/tproger",      # IT новости
    "https://t.me/rbc_news",     # РБК
    "https://t.me/lenta_ru",     # Лента.ру
    "https://t.me/ria_news",     # РИА Новости
    "https://t.me/kommersant_ru", # Коммерсантъ
    "https://t.me/vedomosti",    # Ведомости
    "https://t.me/izvestia_ru",  # Известия
    "https://t.me/mk_ru",        # МК
]

NEWS_SOURCES = {
    "habr": "https://habr.com/ru/rss/all/",
    "tproger": "https://tproger.ru/feed/",
    "vc": "https://vc.ru/feed"
}