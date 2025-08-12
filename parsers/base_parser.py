import requests
from bs4 import BeautifulSoup  # Убедитесь, что это есть
import feedparser
from typing import List, Dict

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