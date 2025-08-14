#!/usr/bin/env python3
"""
Тест упрощенного бота
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.telegram_parser import TelegramParser
from database.db import init_db, get_user_channels, get_user_news_count
from bot.admin import is_admin

def test_parser():
    """Тестирует парсер"""
    print("=== ТЕСТ ПАРСЕРА ===")
    
    parser = TelegramParser()
    
    # Тестируем парсинг канала
    test_channel = "https://t.me/tproger"
    posts = parser.parse_channel(test_channel, limit=5)
    
    print(f"Получено постов: {len(posts)}")
    for i, post in enumerate(posts, 1):
        print(f"{i}. {post.get('title', 'Без заголовка')[:50]}...")
        print(f"   Канал: {post.get('channel', 'Неизвестный')}")
        print(f"   Дата: {post.get('date', 'Нет даты')}")
        print()

def test_database():
    """Тестирует базу данных"""
    print("=== ТЕСТ БАЗЫ ДАННЫХ ===")
    
    # Инициализируем БД
    init_db()
    
    # Тестируем получение настроек пользователя
    user_id = 1203425573
    channels = get_user_channels(user_id)
    news_count = get_user_news_count(user_id)
    
    print(f"Пользователь {user_id}:")
    print(f"  Каналов: {len(channels) if channels else 0}")
    print(f"  Количество новостей: {news_count}")
    
    if channels:
        print("  Каналы:")
        for channel in channels[:3]:
            print(f"    - {channel}")

def test_admin():
    """Тестирует админские функции"""
    print("=== ТЕСТ АДМИНКИ ===")
    
    # Тестируем проверку админа
    admin_id = 1203425573
    non_admin_id = 123456789
    
    print(f"Пользователь {admin_id} - админ: {is_admin(admin_id)}")
    print(f"Пользователь {non_admin_id} - админ: {is_admin(non_admin_id)}")

def test_top_news():
    """Тестирует получение топ новостей"""
    print("=== ТЕСТ ТОП НОВОСТЕЙ ===")
    
    parser = TelegramParser()
    
    # Тестируем получение популярных постов
    channels = [
        "https://t.me/tproger",
        "https://t.me/rbc_news",
        "https://t.me/lenta_ru"
    ]
    
    posts = parser.get_popular_posts(channels, limit_per_channel=3)
    
    print(f"Всего получено постов: {len(posts)}")
    print("Первые 5 постов:")
    for i, post in enumerate(posts[:5], 1):
        print(f"{i}. {post.get('title', 'Без заголовка')[:60]}...")
        print(f"   Канал: {post.get('channel', 'Неизвестный')}")

if __name__ == "__main__":
    print("🧪 ТЕСТИРОВАНИЕ УПРОЩЕННОГО БОТА")
    print("=" * 50)
    
    try:
        test_parser()
        print()
        test_database()
        print()
        test_admin()
        print()
        test_top_news()
        print()
        
        print("✅ Все тесты пройдены успешно!")
        print("🎉 Упрощенный бот готов к работе!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
