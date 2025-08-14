from .base_parser import BaseParser
from typing import List, Dict
from bs4 import BeautifulSoup
import requests
from urllib.parse import quote
import feedparser
import re

class HabrParser(BaseParser):
    def _clean_html_text(self, html_text: str) -> str:
        """Очищает HTML-теги из текста, оставляя только чистый текст"""
        if not html_text:
            return ""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, 'html.parser')
            return soup.get_text(strip=True)
        except Exception:
            # Если не удалось очистить, возвращаем как есть
            return html_text
    
    def get_latest_news(self, limit: int = 10) -> List[Dict]:
        """Получение последних новостей с Habr"""
        try:
            # Сначала пробуем RSS feed для более надежного получения изображений
            rss_url = "https://habr.com/ru/rss/all/"
            feed = feedparser.parse(rss_url)
            
            if feed.entries:
                articles = []
                for entry in feed.entries[:limit]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    summary = entry.get('summary', '')
                    published = entry.get('published', '')
                    
                    # Ищем изображение в RSS
                    image_url = ''
                    
                    # Пробуем найти изображение в media_content
                    if hasattr(entry, 'media_content') and entry.media_content:
                        for media in entry.media_content:
                            if media.get('type', '').startswith('image/'):
                                image_url = media.get('url', '')
                                if image_url:
                                    break
                    
                    # Если не нашли в media_content, пробуем media_thumbnail
                    if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                        for thumb in entry.media_thumbnail:
                            image_url = thumb.get('url', '')
                            if image_url:
                                break
                    
                    # Если все еще не нашли, пробуем извлечь из summary
                    if not image_url and summary:
                        # Ищем img теги в summary
                        soup = BeautifulSoup(summary, 'html.parser')
                        img_tag = soup.find('img')
                        if img_tag and img_tag.get('src'):
                            image_url = img_tag.get('src')
                    
                    # Нормализуем URL изображения
                    if image_url:
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = 'https://habr.com' + image_url
                        elif not image_url.startswith('http'):
                            image_url = 'https://habr.com' + image_url
                        
                        # Улучшаем качество изображения
                        if '/r/w48/' in image_url:
                            image_url = image_url.replace('/r/w48/', '/r/w1200/')
                        elif '/r/w96/' in image_url:
                            image_url = image_url.replace('/r/w96/', '/r/w1200/')
                        elif '/r/w156/' in image_url:
                            image_url = image_url.replace('/r/w156/', '/r/w1200/')
                        elif '/r/w312/' in image_url:
                            image_url = image_url.replace('/r/w312/', '/r/w1200/')
                        elif '/r/w624/' in image_url:
                            image_url = image_url.replace('/r/w624/', '/r/w1200/')
                        
                        # Пробуем оригинал без размеров
                        if '/r/w' in image_url:
                            original_url = re.sub(r'/r/w\d+/', '/', image_url)
                            if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                image_url = original_url
                    
                    # Очищаем summary от HTML тегов
                    if summary:
                        soup = BeautifulSoup(summary, 'html.parser')
                        summary = soup.get_text(separator=' ', strip=True)
                    
                    articles.append({
                        'title': title,
                        'link': link,
                        'summary': summary[:200] + '...' if len(summary) > 200 else summary,
                        'date': published,
                        'source': 'habr.com',
                        'image_url': image_url
                    })
                
                if articles:
                    return articles
            
            # Если RSS не сработал, используем HTML парсинг как fallback
            return self._parse_habr_html(limit)
            
        except Exception as e:
            print(f"Ошибка при получении новостей с Habr: {e}")
            # Fallback к HTML парсингу
            return self._parse_habr_html(limit)
    
    def _parse_habr_html(self, limit: int) -> List[Dict]:
        """HTML парсинг Habr как fallback"""
        try:
            # Получаем главную страницу Habr
            response = self.session.get("https://habr.com/ru/", timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем статьи на главной странице
            article_elements = soup.select('.tm-articles-list__item, .article, .post')
            
            articles = []
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
                    
                    # Ищем изображение
                    image_url = ''
                    
                    # Попробуем разные селекторы для изображений
                    img_selectors = [
                        '.tm-article-snippet__cover img',  # Обложка статьи
                        '.article__cover img',  # Альтернативный селектор
                        '.post__cover img',  # Еще один вариант
                        'img[src*=".jpg"]',  # JPG изображения
                        'img[src*=".png"]',  # PNG изображения
                        'img[src*=".webp"]',  # WebP изображения
                        'img'  # Любое изображение как fallback
                    ]
                    
                    for selector in img_selectors:
                        img_elem = article.select_one(selector)
                        if img_elem and img_elem.get('src'):
                            image_url = img_elem.get('src')
                            
                            # Пропускаем только явные аватары
                            if 'avatar' in image_url.lower() and 'upload_files' not in image_url:
                                continue
                            
                            # Проверяем, что это действительно изображение
                            if any(ext in image_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                break
                            # Если нет расширения, но есть habr.com в URL
                            elif 'habr.com' in image_url:
                                break
                    
                    # Если нашли изображение, нормализуем URL
                    if image_url:
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = 'https://habr.com' + image_url
                        elif not image_url.startswith('http'):
                            image_url = 'https://habr.com' + image_url
                        
                        # Улучшаем качество изображения
                        # Заменяем уменьшенные версии на оригинальные
                        if '/r/w48/' in image_url:
                            # w48 = 48px ширина, заменяем на w1200 (1200px)
                            image_url = image_url.replace('/r/w48/', '/r/w1200/')
                        elif '/r/w96/' in image_url:
                            # w96 = 96px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w96/', '/r/w1200/')
                        elif '/r/w156/' in image_url:
                            # w156 = 156px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w156/', '/r/w1200/')
                        elif '/r/w312/' in image_url:
                            # w312 = 312px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w312/', '/r/w1200/')
                        elif '/r/w624/' in image_url:
                            # w624 = 624px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w624/', '/r/w1200/')
                        
                        # Также пробуем найти оригинальное изображение без размеров
                        if '/r/w' in image_url:
                            # Убираем размеры полностью для получения оригинала
                            original_url = re.sub(r'/r/w\d+/', '/', image_url)
                            # Проверяем, что это все еще изображение
                            if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                image_url = original_url
                    
                    # Если не нашли изображение статьи, пробуем найти в CSS background-image
                    if not image_url:
                        style_elem = article.select_one('[style*="background-image"]')
                        if style_elem:
                            style = style_elem.get('style', '')
                            bg_match = re.search(r'background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)', style)
                            if bg_match:
                                bg_url = bg_match.group(1)
                                # Пропускаем только явные аватары
                                if 'avatar' not in bg_url.lower() or 'upload_files' in bg_url:
                                    if bg_url.startswith('//'):
                                        image_url = 'https:' + bg_url
                                    elif bg_url.startswith('/'):
                                        image_url = 'https://habr.com' + bg_url
                                    elif not bg_url.startswith('http'):
                                        image_url = 'https://habr.com' + bg_url
                                    
                                    # Улучшаем качество CSS изображения
                                    if '/r/w48/' in image_url:
                                        image_url = image_url.replace('/r/w48/', '/r/w1200/')
                                    elif '/r/w96/' in image_url:
                                        image_url = image_url.replace('/r/w96/', '/r/w1200/')
                                    elif '/r/w156/' in image_url:
                                        image_url = image_url.replace('/r/w156/', '/r/w1200/')
                                    elif '/r/w312/' in image_url:
                                        image_url = image_url.replace('/r/w312/', '/r/w1200/')
                                    elif '/r/w624/' in image_url:
                                        image_url = image_url.replace('/r/w624/', '/r/w1200/')
                                    
                                    # Пробуем оригинал без размеров
                                    if '/r/w' in image_url:
                                        original_url = re.sub(r'/r/w\d+/', '/', image_url)
                                        if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                            image_url = original_url
                    
                    if title and link:
                        # Очищаем HTML из summary
                        clean_summary = self._clean_html_text(summary)
                        summary = clean_summary[:200] + '...' if len(clean_summary) > 200 else summary
                        
                        articles.append({
                            'title': title,
                            'link': link,
                            'summary': summary,
                            'date': date,
                            'source': 'habr.com',
                            'image_url': image_url
                        })
                        
                except Exception as e:
                    continue
            
            return articles[:limit]
            
        except Exception as e:
            print(f"Ошибка при HTML парсинге Habr: {e}")
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
                    
                    # Ищем изображение
                    image_url = ''
                    
                    # Попробуем разные селекторы для изображений
                    img_selectors = [
                        '.tm-article-snippet__cover img',  # Обложка статьи
                        '.article__cover img',  # Альтернативный селектор
                        '.post__cover img',  # Еще один вариант
                        'img[src*=".jpg"]',  # JPG изображения
                        'img[src*=".png"]',  # PNG изображения
                        'img[src*=".webp"]',  # WebP изображения
                        'img'  # Любое изображение как fallback
                    ]
                    
                    for selector in img_selectors:
                        img_elem = article.select_one(selector)
                        if img_elem and img_elem.get('src'):
                            image_url = img_elem.get('src')
                            
                            # Пропускаем только явные аватары
                            if any(skip_word in image_url.lower() for skip_word in ['avatar', 'emoji', 'smile', 'icon']):
                                continue
                            
                            # Пропускаем изображения с определенными размерами (обычно аватары)
                            if any(size in image_url for size in ['/r/w48/', '/r/w96/', '/r/w156/', '/r/w312/', '/r/w624/']):
                                continue
                            
                            # Проверяем, что это действительно изображение статьи
                            if any(ext in image_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                # Дополнительная проверка - пропускаем аватары по размеру
                                if 'upload_files' in image_url or 'habr' in image_url:
                                    break
                            # Если нет расширения, но есть habr.com в URL
                            elif 'habr.com' in image_url and 'upload_files' in image_url:
                                break
                    
                    # Если нашли изображение, нормализуем URL
                    if image_url:
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = 'https://habr.com' + image_url
                        elif not image_url.startswith('http'):
                            image_url = 'https://habr.com' + image_url
                        
                        # Улучшаем качество изображения
                        # Заменяем уменьшенные версии на оригинальные
                        if '/r/w48/' in image_url:
                            # w48 = 48px ширина, заменяем на w1200 (1200px)
                            image_url = image_url.replace('/r/w48/', '/r/w1200/')
                        elif '/r/w96/' in image_url:
                            # w96 = 96px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w96/', '/r/w1200/')
                        elif '/r/w156/' in image_url:
                            # w156 = 156px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w156/', '/r/w1200/')
                        elif '/r/w312/' in image_url:
                            # w312 = 312px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w312/', '/r/w1200/')
                        elif '/r/w624/' in image_url:
                            # w624 = 624px ширина, заменяем на w1200
                            image_url = image_url.replace('/r/w624/', '/r/w1200/')
                        
                        # Также пробуем найти оригинальное изображение без размеров
                        if '/r/w' in image_url:
                            # Убираем размеры полностью для получения оригинала
                            original_url = re.sub(r'/r/w\d+/', '/', image_url)
                            # Проверяем, что это все еще изображение
                            if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                image_url = original_url
                    
                    # Если не нашли изображение статьи, пробуем найти в CSS background-image
                    if not image_url:
                        style_elem = article.select_one('[style*="background-image"]')
                        if style_elem:
                            style = style_elem.get('style', '')
                            bg_match = re.search(r'background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)', style)
                            if bg_match:
                                bg_url = bg_match.group(1)
                                # Пропускаем только явные аватары
                                if not any(skip_word in bg_url.lower() for skip_word in ['avatar', 'emoji', 'smile', 'icon']):
                                    if bg_url.startswith('//'):
                                        image_url = 'https:' + bg_url
                                    elif bg_url.startswith('/'):
                                        image_url = 'https://habr.com' + bg_url
                                    elif not bg_url.startswith('http'):
                                        image_url = 'https://habr.com' + bg_url
                                    
                                    # Улучшаем качество CSS изображения
                                    if '/r/w48/' in image_url:
                                        image_url = image_url.replace('/r/w48/', '/r/w1200/')
                                    elif '/r/w96/' in image_url:
                                        image_url = image_url.replace('/r/w96/', '/r/w1200/')
                                    elif '/r/w156/' in image_url:
                                        image_url = image_url.replace('/r/w156/', '/r/w1200/')
                                    elif '/r/w312/' in image_url:
                                        image_url = image_url.replace('/r/w312/', '/r/w1200/')
                                    elif '/r/w624/' in image_url:
                                        image_url = image_url.replace('/r/w624/', '/r/w1200/')
                                    
                                    # Пробуем оригинал без размеров
                                    if '/r/w' in image_url:
                                        original_url = re.sub(r'/r/w\d+/', '/', image_url)
                                        if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                                            image_url = original_url
                    
                    if title and link:
                        # Очищаем HTML из summary
                        clean_summary = self._clean_html_text(summary)
                        summary = clean_summary[:200] + '...' if len(clean_summary) > 200 else clean_summary
                        
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': summary,
                            'date': '',
                            'source': 'habr.com',
                            'image_url': image_url
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
            
            # Парсим RSS
            feed = feedparser.parse(rss_url)
            posts = []
            
            for entry in feed.entries[:limit]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                summary = entry.get('summary', '')
                published = entry.get('published', '')
                
                # Ищем изображение в RSS
                image_url = ''
                
                # Пробуем найти изображение в media_content
                if hasattr(entry, 'media_content') and entry.media_content:
                    for media in entry.media_content:
                        if media.get('type', '').startswith('image/'):
                            image_url = media.get('url', '')
                            if image_url:
                                break
                
                # Если не нашли в media_content, пробуем media_thumbnail
                if not image_url and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                    for thumb in entry.media_thumbnail:
                        image_url = thumb.get('url', '')
                        if image_url:
                            break
                
                # Если все еще не нашли, пробуем извлечь из summary
                if not image_url and summary:
                    # Ищем img теги в summary
                    soup = BeautifulSoup(summary, 'html.parser')
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'):
                        image_url = img_tag.get('src')
                
                # Нормализуем URL изображения
                if image_url:
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    elif image_url.startswith('/'):
                        image_url = 'https://habr.com' + image_url
                    elif not image_url.startswith('http'):
                        image_url = 'https://habr.com' + image_url
                    
                    # Улучшаем качество изображения
                    if '/r/w48/' in image_url:
                        image_url = image_url.replace('/r/w48/', '/r/w1200/')
                    elif '/r/w96/' in image_url:
                        image_url = image_url.replace('/r/w96/', '/r/w1200/')
                    elif '/r/w156/' in image_url:
                        image_url = image_url.replace('/r/w156/', '/r/w1200/')
                    elif '/r/w312/' in image_url:
                        image_url = image_url.replace('/r/w312/', '/r/w1200/')
                    elif '/r/w624/' in image_url:
                        image_url = image_url.replace('/r/w624/', '/r/w1200/')
                    
                    # Пробуем оригинал без размеров
                    if '/r/w' in image_url:
                        original_url = re.sub(r'/r/w\d+/', '/', image_url)
                        if any(ext in original_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                            image_url = original_url
                
                # Очищаем summary от HTML тегов
                if summary:
                    soup = BeautifulSoup(summary, 'html.parser')
                    summary = soup.get_text(separator=' ', strip=True)
                
                posts.append({
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'date': published,
                    'image_url': image_url,
                    'source': 'habr.com'
                })
            
            return posts
            
        except Exception as e:
            print(f"Ошибка при получении дополнительных новостей с Habr: {e}")
            return []