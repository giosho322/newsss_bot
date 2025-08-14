from .base_parser import BaseParser
from typing import List, Dict
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote
import feedparser

class HabrParser(BaseParser):
    def get_latest_news(self, limit: int = 10) -> List[Dict]:
        """Получение последних IT новостей с Habr"""
        try:
            response = self.session.get("https://habr.com/ru/", timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            articles = []
            # Ищем статьи на главной странице
            article_elements = soup.select('.tm-articles-list__item, .article, .post')
            
            for article in article_elements[:limit * 2]:  # Берем больше для лучшего выбора
                try:
                    title_elem = article.select_one('.tm-title a, h2 a, h3 a, .post__title a')
                    if not title_elem:
                        continue
                        
                    title = title_elem.get_text().strip()
                    link = title_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://habr.com{link}"
                    
                    # Ищем краткое описание
                    summary_elem = article.select_one('.article__descr, .post__text, .tm-article-snippet')
                    summary = summary_elem.get_text().strip() if summary_elem else ''
                    
                    # Ищем дату
                    date_elem = article.select_one('.tm-article-meta__date, .post__date, time')
                    date = date_elem.get_text().strip() if date_elem else ''
                    
                    if title and link:
                        articles.append({
                            'title': title,
                            'link': link,
                            'summary': summary[:200] + '...' if len(summary) > 200 else summary,
                            'date': date,
                            'source': 'habr.com'
                        })
                        
                except Exception as e:
                    continue
            
            return articles[:limit]
            
        except Exception as e:
            print(f"Ошибка при получении новостей с Habr: {e}")
            return []
    
    def search_by_query(self, query: str, limit: int = 10) -> List[Dict]:
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
            articles = soup.select('.tm-articles-list__item, .article, .post, .tm-article-card')
            
            news_list = []
            for article in articles:
                title_elem = article.select_one('.tm-title a, h2 a, h3 a, .tm-article-card__title a')
                if title_elem:
                    title = title_elem.get_text().strip()
                    link = title_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://habr.com{link}"
                    
                    # Ищем краткое описание
                    summary_elem = article.select_one('.article__descr, .post__text, .tm-article-snippet, .tm-article-card__snippet')
                    summary = summary_elem.get_text().strip() if summary_elem else ''
                    
                    if title and link:
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': summary[:200] + '...' if len(summary) > 200 else summary,
                            'date': '',
                            'source': 'habr.com'
                        })
            
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
            content = soup.select_one('.article-formatted-body, .post__text, .tm-article-body, .tm-article-content')
            
            if content:
                # Удаляем скрипты и стили
                for script in content(["script", "style", "aside", ".tm-article-comments", "noscript", "iframe"]):
                    script.decompose()
                
                # Получаем текст
                full_text = content.get_text(strip=False)
                full_text = ' '.join(full_text.split())
                
                # Получаем заголовок
                title_elem = soup.select_one('h1.tm-title, .post__title, h1, title')
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

    def get_more_news(self, offset: int = 0, limit: int = 5) -> List[Dict]:
        """Получение дополнительных новостей с Habr (для кнопки 'Еще')"""
        try:
            # Используем RSS для получения большего количества новостей
            rss_url = "https://habr.com/ru/rss/all/"
            feed = feedparser.parse(rss_url)
            
            articles = []
            start_idx = offset
            end_idx = start_idx + limit
            
            for entry in feed.entries[start_idx:end_idx]:
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'summary': getattr(entry, 'summary', '')[:200] + '...' if len(getattr(entry, 'summary', '')) > 200 else getattr(entry, 'summary', ''),
                    'date': getattr(entry, 'published', ''),
                    'source': 'habr.com'
                })
            
            return articles
            
        except Exception as e:
            print(f"Ошибка при получении дополнительных новостей с Habr: {e}")
            return []