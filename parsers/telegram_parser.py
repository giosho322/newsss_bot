import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import re
import logging

class TelegramParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def parse_channel(self, channel_url: str, limit: int = 5) -> List[Dict]:
        """
        Парсинг Telegram канала
        channel_url: ссылка на канал (например, https://t.me/channel_name)
        """
        try:
            # Извлекаем имя канала из URL
            if channel_url.startswith('https://t.me/'):
                channel_name = channel_url.split('/')[-1]
            elif channel_url.startswith('@'):
                channel_name = channel_url[1:]
            else:
                channel_name = channel_url
            
            # Формируем URL для публичного просмотра
            html_url = f"https://t.me/s/{channel_name}"
            
            response = self.session.get(html_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем посты на странице
            posts = soup.select('.tgme_widget_message_wrap')[:limit]
            logging.info(f"Найдено {len(posts)} постов в канале {channel_name}")
            
            news_list = []
            for post in posts:
                try:
                    # Извлекаем данные из поста
                    message_link = post.select_one('.tgme_widget_message_date a')
                    if not message_link:
                        continue
                        
                    link = message_link.get('href', '')
                    
                    # Текст поста
                    text_elem = post.select_one('.tgme_widget_message_text')
                    text = text_elem.get_text() if text_elem else ''
                    
                    # Дата поста
                    date_elem = post.select_one('.tgme_widget_message_date time')
                    date_str = date_elem.get('datetime', '') if date_elem else ''
                    
                    # Ищем изображение
                    image_url = ''
                    # Сначала ищем в photo_wrap
                    image_elem = post.select_one('.tgme_widget_message_photo_wrap')
                    if image_elem:
                        style = image_elem.get('style', '')
                        # Извлекаем URL изображения из background-image
                        match = re.search(r"background-image:url\('([^']+)'\)", style)
                        if match:
                            image_url = match.group(1)
                    
                    # Если нет изображения, ищем обычное фото
                    if not image_url:
                        photo_elem = post.select_one('.tgme_widget_message_photo img')
                        if photo_elem:
                            image_url = photo_elem.get('src', '')
                    
                    # Если все еще нет изображения, ищем в attachments
                    if not image_url:
                        attach_elem = post.select_one('.tgme_widget_message_photo')
                        if attach_elem:
                            style = attach_elem.get('style', '')
                            match = re.search(r"background-image:url\('([^']+)'\)", style)
                            if match:
                                image_url = match.group(1)
                    
                    if text or image_url:  # Добавляем пост, если есть текст или изображение
                        news_list.append({
                            'title': text[:100] + '...' if len(text) > 100 else text or 'Без заголовка',
                            'text': text,
                            'link': link,
                            'image_url': image_url,
                            'channel': channel_name,
                            'date': date_str,
                        })
                except Exception as e:
                    print(f"Ошибка при парсинге поста: {e}")
                    continue
            
            # Если основной парсинг не дал результатов, пробуем текстовый прокси
            if not news_list:
                try:
                    logging.info(f"Основной парсинг не дал результатов для {channel_name}, пробуем текстовый прокси")
                    proxy_url = f"https://r.jina.ai/http://t.me/s/{channel_name}"
                    proxy_resp = self.session.get(proxy_url, timeout=20)
                    if proxy_resp.ok and proxy_resp.text:
                        text_page = proxy_resp.text
                        # Ищем ссылки на посты и первые строки как заголовки
                        links = re.findall(r"https://t\.me/[^\s)]+/\d+", text_page)
                        unique_links = []
                        for ln in links:
                            if ln not in unique_links:
                                unique_links.append(ln)
                        for ln in unique_links[:limit]:
                            # Набросок текста вокруг ссылки
                            idx = text_page.find(ln)
                            start = max(0, idx - 200)
                            snippet = text_page[start: idx].splitlines()[-1] if idx != -1 else ''
                            snippet = snippet.strip()
                            title = (snippet[:100] + '...') if len(snippet) > 100 else (snippet or 'Без заголовка')
                            news_list.append({
                                'title': title,
                                'text': snippet,
                                'link': ln,
                                'image_url': '',
                                'channel': channel_name,
                                'date': '',
                            })
                        logging.info(f"Текстовый прокси дал {len(news_list)} постов для {channel_name}")
                except Exception as e:
                    logging.error(f"Ошибка при использовании текстового прокси для {channel_name}: {e}")
                    pass
            
            return news_list
            
        except Exception as e:
            logging.error(f"Ошибка при парсинге канала {channel_url}: {e}")
            return []
    
    def get_popular_posts(self, channels: List[str], limit_per_channel: int = 2) -> List[Dict]:
        """
        Получение популярных постов из списка каналов
        """
        all_posts = []
        
        for channel_url in channels[:3]:  # Ограничиваем до 3 каналов
            try:
                posts = self.parse_channel(channel_url, limit_per_channel * 2)
                all_posts.extend(posts)
            except Exception as e:
                print(f"Ошибка при обработке канала {channel_url}: {e}")
                continue
        
        # Сортируем по дате (новые первыми)
        all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Берем только нужное количество
        return all_posts[:len(channels) * limit_per_channel]