from .base_parser import BaseParser
from typing import List, Dict
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote

class HabrParser(BaseParser):
    def get_latest_news(self, limit: int = 5) -> List[Dict]:
        """Получение последних новостей с Habr"""
        rss_url = "https://habr.com/ru/rss/all/"
        return self.parse_rss(rss_url, limit)
    
    def search_by_theme(self, theme: str, limit: int = 5) -> List[Dict]:
        """Поиск новостей по теме через RSS тегов"""
        theme_urls = {
            "python": "https://habr.com/ru/rss/tag/python/all/",
            "js": "https://habr.com/ru/rss/tag/javascript/all/",
            "ai": "https://habr.com/ru/rss/tag/machine_learning/all/",
            "web": "https://habr.com/ru/rss/tag/webdev/all/"
        }
        
        rss_url = theme_urls.get(theme, "https://habr.com/ru/rss/all/")
        return self.parse_rss(rss_url, limit)
    
    def search_by_query(self, query: str, limit: int = 5) -> List[Dict]:
        """Поиск новостей по произвольному запросу"""
        try:
            # Кодируем запрос для URL
            encoded_query = quote(query)
            search_url = f"https://habr.com/ru/search/?q={encoded_query}"
            
            # Выполняем поиск
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем статьи на странице результатов поиска
            articles = soup.select('.tm-articles-list__item')[:limit] or \
                      soup.select('.article')[:limit] or \
                      soup.select('.post')[:limit]
            
            news_list = []
            for article in articles:
                title_elem = article.select_one('.tm-title a') or article.select_one('h2 a') or article.select_one('h3 a')
                if title_elem:
                    title = title_elem.get_text().strip()
                    link = title_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://habr.com{link}"
                    
                    # Ищем краткое описание
                    summary_elem = article.select_one('.article__descr') or article.select_one('.post__text') or article.select_one('.tm-article-snippet')
                    summary = summary_elem.get_text().strip() if summary_elem else ''
                    
                    if title and link:
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': summary[:200] + '...' if len(summary) > 200 else summary,
                            'published': ''
                        })
            
            # Если не нашли через HTML-парсинг, используем RSS поиска (если доступен)
            if not news_list:
                # Попробуем через RSS (если такой существует)
                # Это упрощенная реализация
                pass
                
            return news_list
            
        except Exception as e:
            print(f"Ошибка поиска по запросу '{query}': {e}")
            # В случае ошибки возвращаем пустой список
            return []
    
    def parse_full_article(self, url: str) -> Dict:
        """Парсинг полной статьи с Habr"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Специфичные селекторы для Habr
            content = soup.select_one('.article-formatted-body') or \
                     soup.select_one('.post__text') or \
                     soup.select_one('.tm-article-body')
            
            if content:
                # Удаляем скрипты и стили
                for script in content(["script", "style", "aside", ".tm-article-comments"]):
                    script.decompose()
                
                # Получаем текст
                full_text = content.get_text(strip=False)
                full_text = ' '.join(full_text.split())
                
                # Получаем заголовок
                title_elem = soup.select_one('h1.tm-title') or soup.find('title')
                title = title_elem.get_text().strip() if title_elem else 'Без заголовка'
                
                # Ограничиваем длину
                if len(full_text) > 3000:
                    full_text = full_text[:3000] + '...\n\n(Продолжение на сайте)'
                
                return {
                    'success': True,
                    'content': full_text,
                    'title': title
                }
            else:
                # Если не нашли специфичный контент, используем базовый метод
                return super().parse_full_article(url)
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка при парсинге статьи Habr: {str(e)}'
            }