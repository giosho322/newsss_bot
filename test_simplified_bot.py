#!/usr/bin/env python3
"""
Тест для проверки работы парсеров
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_habr_parser():
    """Тестируем Habr парсер"""
    print("=== Тест Habr парсера ===")
    try:
        from parsers.habr_parser import HabrParser
        parser = HabrParser()
        
        # Тестируем получение новостей
        print("Получаем последние новости...")
        news = parser.get_latest_news(limit=3)
        
        for i, post in enumerate(news):
            print(f"\nНовость {i+1}:")
            print(f"  Заголовок: {post.get('title', 'Нет')}")
            print(f"  Ссылка: {post.get('link', 'Нет')}")
            print(f"  Изображение: {post.get('image_url', 'НЕТ!')}")
            print(f"  Источник: {post.get('source', 'Нет')}")
        
        # Тестируем поиск
        print("\nТестируем поиск...")
        search_results = parser.search_by_query("python", limit=2)
        
        for i, post in enumerate(search_results):
            print(f"\nРезультат поиска {i+1}:")
            print(f"  Заголовок: {post.get('title', 'Нет')}")
            print(f"  Ссылка: {post.get('link', 'Нет')}")
            print(f"  Изображение: {post.get('image_url', 'НЕТ!')}")
            print(f"  Источник: {post.get('source', 'Нет')}")
            
    except Exception as e:
        print(f"Ошибка в Habr парсере: {e}")
        import traceback
        traceback.print_exc()

def test_telegram_parser():
    """Тестируем Telegram парсер"""
    print("\n=== Тест Telegram парсера ===")
    try:
        from parsers.telegram_parser import TelegramParser
        parser = TelegramParser()
        
        # Тестируем парсинг канала
        print("Парсим канал...")
        posts = parser.parse_channel("https://t.me/rbc_news", limit=3)
        
        for i, post in enumerate(posts):
            print(f"\nПост {i+1}:")
            print(f"  Заголовок: {post.get('title', 'Нет')}")
            print(f"  Ссылка: {post.get('link', 'Нет')}")
            print(f"  Изображение: {post.get('image_url', 'НЕТ!')}")
            print(f"  Видео: {post.get('video_url', 'НЕТ!')}")
            print(f"  Анимация: {post.get('animation_url', 'НЕТ!')}")
            print(f"  Канал: {post.get('channel', 'Нет')}")
            
    except Exception as e:
        print(f"Ошибка в Telegram парсере: {e}")
        import traceback
        traceback.print_exc()

def test_collect_posts():
    """Тестируем функцию _collect_posts"""
    print("\n=== Тест _collect_posts ===")
    try:
        # Импортируем необходимые модули
        from bot.main import _collect_posts
        import asyncio
        
        # Запускаем асинхронную функцию
        posts = asyncio.run(_collect_posts(days=1))
        
        print(f"Получено постов: {len(posts)}")
        
        for i, post in enumerate(posts[:3]):
            print(f"\nПост {i+1}:")
            print(f"  Заголовок: {post.get('title', 'Нет')}")
            print(f"  Ссылка: {post.get('link', 'Нет')}")
            print(f"  Изображение: {post.get('image_url', 'НЕТ!')}")
            print(f"  Видео: {post.get('video_url', 'НЕТ!')}")
            print(f"  Анимация: {post.get('animation_url', 'НЕТ!')}")
            print(f"  Канал: {post.get('channel', 'Нет')}")
            
    except Exception as e:
        print(f"Ошибка в _collect_posts: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Запускаем тесты парсеров...")
    test_habr_parser()
    test_telegram_parser()
    test_collect_posts()
    print("\nТесты завершены!")
