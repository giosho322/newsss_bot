#!/usr/bin/env python3
"""
Парсер для Telegram каналов
Упрощенная версия без фильтров
"""

import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

class TelegramParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def parse_channel(self, channel_url: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Парсит канал и возвращает список постов
        Убраны все фильтры, только сортировка по дате
        """
        try:
            # Извлекаем имя канала из URL
            channel_name = channel_url.split('/')[-1]
            logger.info(f"Парсим канал: {channel_name} (URL: {channel_url})")
            
            # Формируем URL для парсинга
            parse_url = f"https://t.me/s/{channel_name}"
            
            # Получаем страницу
            response = self.session.get(parse_url, timeout=10)
            response.raise_for_status()
            
            # Парсим HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем все посты
            posts = soup.select('.tgme_widget_message')
            logger.info(f"Найдено {len(posts)} потенциальных постов в канале {channel_name}")
            
            extracted_posts = []
            
            for post in posts[:limit * 2]:  # Берем больше постов для лучшего выбора
                try:
                    post_data = self._extract_post_data(post, channel_name)
                    if post_data:
                        extracted_posts.append(post_data)
                except Exception as e:
                    logger.debug(f"Ошибка при извлечении поста: {e}")
                    continue
            
            # Сортируем по дате (новые сначала)
            extracted_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            # Возвращаем ограниченное количество
            result = extracted_posts[:limit]
            
            logger.info(f"Успешно извлечено постов: {len(result)} из {channel_name}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге канала {channel_url}: {e}")
            return []

    def _extract_post_data(self, post_element, channel_name: str) -> Dict[str, Any]:
        """Извлекает данные из поста"""
        try:
            # Извлекаем текст поста
            text_element = post_element.select_one('.tgme_widget_message_text')
            if not text_element:
                return None
            
            text = text_element.get_text(strip=True)
            if not text or len(text) < 10:  # Минимальная длина текста
                return None
            
            # Извлекаем заголовок (первые 100 символов)
            title = text[:100] + "..." if len(text) > 100 else text
            
            # Извлекаем ссылку на пост
            message_link = post_element.select_one('.tgme_widget_message_date a')
            if not message_link:
                # Альтернативный способ поиска ссылки
                all_links = post_element.select('a')
                message_link = None
                for link_elem in all_links:
                    href = link_elem.get('href', '')
                    if href and '/' in href and href.split('/')[-1].isdigit():
                        message_link = link_elem
                        break
                if not message_link:
                    return None
            
            link = message_link.get('href', '')
            if not link:
                return None
            
            # Извлекаем дату (пытаемся взять явный datetime)
            date_str = ""
            time_el = post_element.select_one('.tgme_widget_message_date time')
            if time_el and time_el.get('datetime'):
                try:
                    iso = time_el.get('datetime')
                    # 2024-08-13T11:24:00+00:00 -> 2024-08-13
                    date_str = iso.split('T', 1)[0]
                except Exception:
                    date_str = ""
            if not date_str:
                date_element = post_element.select_one('.tgme_widget_message_date')
                if date_element:
                    date_text = date_element.get_text(strip=True)
                    date_str = self._parse_date(date_text)
            
            # Извлекаем количество просмотров
            views_element = post_element.select_one('.tgme_widget_message_views')
            views = 0
            if views_element:
                views_text = views_element.get_text(strip=True)
                views = self._parse_views(views_text)

            # Извлекаем превью-изображение/видео/гиф, если есть
            image_url = ''
            video_url = ''
            animation_url = ''
            photo_wrap = post_element.select_one('.tgme_widget_message_photo_wrap')
            if photo_wrap:
                style = photo_wrap.get('style', '')
                # Возможные варианты: url('...'), url("..."), url(...)
                m = re.search(r'''background-image:\s*url\((?:'|")?([^'")]+)(?:'|")?\)''', style)
                if m:
                    image_url = m.group(1)
            if not image_url:
                img_tag = post_element.select_one('.tgme_widget_message_photo img, img.tgme_widget_message_photo')
                if img_tag and img_tag.get('src'):
                    image_url = img_tag.get('src')

            # Пытаемся извлечь видео (mp4)
            try:
                src_tag = post_element.select_one('video source') or post_element.select_one('video')
                if src_tag and src_tag.get('src'):
                    video_url = src_tag.get('src')
            except Exception:
                pass
            if not video_url:
                a_mp4 = post_element.select_one('a[href$=".mp4"]')
                if a_mp4 and a_mp4.get('href'):
                    video_url = a_mp4.get('href')
            if not video_url:
                any_data_video = post_element.select_one('[data-video]')
                if any_data_video and any_data_video.get('data-video'):
                    video_url = any_data_video.get('data-video')

            # Пытаемся извлечь анимацию/GIF
            a_gif = post_element.select_one('a[href$=".gif"]')
            if a_gif and a_gif.get('href'):
                animation_url = a_gif.get('href')
            if not animation_url:
                img_gif = post_element.select_one('img[src$=".gif"]')
                if img_gif and img_gif.get('src'):
                    animation_url = img_gif.get('src')
            
            return {
                'title': title,
                'text': text,
                'link': link,
                'channel': channel_name,
                'date': date_str,
                'views': views,
                'channel_url': f"https://t.me/{channel_name}",
                'image_url': image_url,
                'video_url': video_url,
                'animation_url': animation_url,
            }
            
        except Exception as e:
            logger.debug(f"Ошибка при извлечении данных поста: {e}")
            return None

    def _parse_date(self, date_text: str) -> str:
        """Парсит дату из текста"""
        try:
            # Простой парсинг даты
            if 'сегодня' in date_text.lower():
                return datetime.now().strftime('%Y-%m-%d')
            elif 'вчера' in date_text.lower():
                yesterday = datetime.now() - timedelta(days=1)
                return yesterday.strftime('%Y-%m-%d')
            else:
                # Пытаемся извлечь дату из текста
                date_pattern = r'(\d{1,2})\.(\d{1,2})\.(\d{4})'
                match = re.search(date_pattern, date_text)
                if match:
                    day, month, year = match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                else:
                    return datetime.now().strftime('%Y-%m-%d')
        except:
            return datetime.now().strftime('%Y-%m-%d')

    def _parse_views(self, views_text: str) -> int:
        """Парсит количество просмотров"""
        try:
            # Убираем все кроме цифр
            views = re.sub(r'[^\d]', '', views_text)
            return int(views) if views else 0
        except:
            return 0

    def get_popular_posts(self, channels: List[str], limit_per_channel: int = 10) -> List[Dict[str, Any]]:
        """
        Получает популярные посты со всех каналов
        Убраны фильтры, только сортировка по дате
        """
        all_posts = []
        
        for channel_url in channels:
            try:
                posts = self.parse_channel(channel_url, limit_per_channel)
                all_posts.extend(posts)
            except Exception as e:
                logger.error(f"Ошибка при парсинге канала {channel_url}: {e}")
                continue
        
        if not all_posts:
            logger.warning("Не удалось получить посты ни с одного канала")
            return []
        
        # Сортируем по дате (новые сначала)
        all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Возвращаем все посты (убрали ограничение)
        return all_posts