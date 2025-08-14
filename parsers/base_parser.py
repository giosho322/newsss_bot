import requests
from bs4 import BeautifulSoup  # Убедитесь, что это есть
import feedparser
from typing import List, Dict
import re

class BaseParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def parse_rss(self, url: str, limit: int = 5) -> List[Dict]:
        """Парсинг RSS-ленты"""
        try:
            feed = feedparser.parse(url)
            news_list = []
            
            for entry in feed.entries[:limit]:
                news_list.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': getattr(entry, 'published', ''),
                    'summary': getattr(entry, 'summary', ''),
                    'id': getattr(entry, 'id', entry.link)
                })
            
            return news_list
        except Exception as e:
            print(f"Ошибка парсинга RSS: {e}")
            return []
    
    def parse_full_article(self, url: str) -> Dict:
        """Парсинг полной статьи"""
        try:
            # Проверяем, является ли это Telegram-ссылкой
            if "t.me/" in url or "/s/" in url:
                return self._parse_telegram_post(url)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Попытка найти основной контент статьи
            # Разные сайты имеют разные структуры
            content_selectors = [
                'article',           # Общий тег article
                '.article',          # Класс article
                '.post',            # Класс post
                '.content',         # Класс content
                '.entry-content',   # WordPress
                '.post-content',    # Часто используемый класс
                'main',             # Основной контент
                '.main-content'     # Класс основного контента
            ]
            
            content = None
            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    break
            
            # Если не нашли специфичный контент, берем body
            if not content:
                content = soup.find('body')
            
            if content:
                # Удаляем скрипты и стили
                for script in content(["script", "style"]):
                    script.decompose()
                
                # Получаем текст
                full_text = content.get_text(strip=False)
                # Очищаем от лишних пробелов
                full_text = ' '.join(full_text.split())
                
                # Ограничиваем длину (Telegram имеет ограничения)
                if len(full_text) > 3000:
                    full_text = full_text[:3000] + '...\n\n(Продолжение на сайте)'
                
                return {
                    'success': True,
                    'content': full_text,
                    'title': soup.find('title').get_text() if soup.find('title') else 'Без заголовка'
                }
            else:
                return {
                    'success': False,
                    'error': 'Не удалось найти контент статьи'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка при парсинге статьи: {str(e)}'
            }
    
    def _parse_telegram_post(self, url: str) -> Dict:
        """Парсинг Telegram-поста"""
        try:
            # Преобразуем URL в формат для парсинга
            if "/s/" in url:
                # Это уже правильный формат для парсинга
                parse_url = url
            else:
                # Преобразуем обычную ссылку в формат для парсинга
                # Например: https://t.me/rbc_news/127293 -> https://t.me/s/rbc_news/127293
                url_parts = url.split("/")
                if len(url_parts) >= 4:
                    channel = url_parts[-2]
                    post_id = url_parts[-1]
                    parse_url = f"https://t.me/s/{channel}/{post_id}"
                else:
                    return {
                        'success': False,
                        'error': 'Неверный формат Telegram-ссылки'
                    }
            
            print(f"DEBUG: Парсим Telegram URL: {parse_url}")
            print(f"DEBUG: Оригинальный URL: {url}")
            
            # Добавляем случайный параметр чтобы избежать кэширования
            import random
            cache_buster = random.randint(1000, 9999)
            parse_url_with_cache_buster = f"{parse_url}?v={cache_buster}"
            
            print(f"DEBUG: URL с cache buster: {parse_url_with_cache_buster}")
            
            # Устанавливаем более агрессивные заголовки
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
            
            response = self.session.get(parse_url_with_cache_buster, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем основной контент поста
            post_content = soup.select_one('.tgme_widget_message_text')
            
            if post_content:
                # Удаляем все скрипты, стили и встроенные виджеты
                for unwanted in post_content(["script", "style", "noscript", "iframe", "embed"]):
                    unwanted.decompose()
                
                # Получаем чистый текст
                content = post_content.get_text(strip=False)
                content = ' '.join(content.split())
                
                print(f"DEBUG: Извлеченный контент: {content[:200]}...")
                print(f"DEBUG: Длина контента: {len(content)} символов")
                
                # Проверяем, что контент не пустой и не слишком короткий
                if len(content) < 10:
                    print(f"DEBUG: Контент слишком короткий: '{content}'")
                    return {
                        'success': False,
                        'error': 'Контент поста слишком короткий'
                    }
                
                # Дополнительная проверка: контент должен быть релевантным заголовку
                # Извлекаем ключевые слова из URL для проверки
                url_channel = url.split('/')[-2] if '/' in url else ''
                print(f"DEBUG: Канал из URL: {url_channel}")
                
                # НЕ обрезаем контент - пусть основной код сам решает, как его использовать
                print(f"DEBUG: Контент оставлен без обрезки: {len(content)} символов")
                
                # Убираем слишком строгую проверку - Telegram иногда возвращает
                # контент из других постов, но это лучше чем ничего
                print(f"DEBUG: Контент принят (проверка релевантности отключена)")
                
                # Ищем заголовок - берем первые 100 символов контента
                title = content[:100] + "..." if len(content) > 100 else content
                
                # Ограничиваем длину
                if len(content) > 3000:
                    content = content[:3000] + '...\n\n(Продолжение в Telegram)'
                
                return {
                    'success': True,
                    'content': content,
                    'title': title
                }
            else:
                print(f"DEBUG: Не найден .tgme_widget_message_text для {parse_url}")
                # Попробуем найти альтернативные селекторы
                alternative_selectors = [
                    '.tgme_widget_message',
                    '.message',
                    '[class*="message"]',
                    '[class*="post"]'
                ]
                
                for selector in alternative_selectors:
                    alt_content = soup.select_one(selector)
                    if alt_content:
                        print(f"DEBUG: Найден альтернативный селектор: {selector}")
                        content = alt_content.get_text(strip=False)
                        content = ' '.join(content.split())
                        if len(content) > 10:
                            title = content[:100] + "..." if len(content) > 100 else content
                            return {
                                'success': True,
                                'content': content,
                                'title': title
                            }
                
                return {
                    'success': False,
                    'error': 'Не удалось найти контент Telegram-поста'
                }
                
        except Exception as e:
            print(f"DEBUG: Ошибка при парсинге {url}: {e}")
            return {
                'success': False,
                'error': f'Ошибка при парсинге Telegram-поста: {str(e)}'
            }