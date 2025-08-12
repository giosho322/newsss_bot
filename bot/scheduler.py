import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import pytz
from database.db import (
    get_digest_schedule, 
    get_user_channels, 
    get_user_filters, 
    get_user_news_count,
    add_notification,
    update_user_activity,
    get_active_users
)
from parsers.telegram_parser import TelegramParser
from bot.utils import apply_filters, clean_html

logger = logging.getLogger(__name__)

class NewsScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.tg_parser = TelegramParser()
        self.running = False
        self.tasks = []
    
    async def start(self):
        """Запускает планировщик."""
        self.running = True
        logger.info("Планировщик новостей запущен")
        
        # Запускаем основную задачу планировщика
        asyncio.create_task(self._scheduler_loop())
        
        # Запускаем задачу очистки старых данных
        asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Останавливает планировщик."""
        self.running = False
        for task in self.tasks:
            task.cancel()
        logger.info("Планировщик новостей остановлен")
    
    async def _scheduler_loop(self):
        """Основной цикл планировщика."""
        while self.running:
            try:
                await self._check_and_send_digests()
                await asyncio.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(300)  # При ошибке ждем 5 минут
    
    async def _cleanup_loop(self):
        """Цикл очистки старых данных."""
        while self.running:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600)  # Очищаем каждый час
            except Exception as e:
                logger.error(f"Ошибка при очистке данных: {e}")
                await asyncio.sleep(3600)
    
    async def _check_and_send_digests(self):
        """Проверяет и отправляет дайджесты по расписанию."""
        try:
            # Получаем всех активных пользователей
            active_users = get_active_users(24)  # За последние 24 часа
            
            for user_id in active_users:
                try:
                    await self._check_user_digest(user_id)
                except Exception as e:
                    logger.error(f"Ошибка при проверке дайджеста для пользователя {user_id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке дайджестов: {e}")
    
    async def _check_user_digest(self, user_id: int):
        """Проверяет, нужно ли отправить дайджест пользователю."""
        try:
            schedule = get_digest_schedule(user_id)
            if not schedule or not schedule['is_active']:
                return
            
            current_time = datetime.now()
            user_timezone = pytz.timezone('UTC')  # По умолчанию UTC
            
            # Парсим время из расписания
            try:
                scheduled_time = datetime.strptime(schedule['time'], '%H:%M').time()
                current_user_time = current_time.astimezone(user_timezone).time()
                
                # Проверяем, пора ли отправлять дайджест
                if self._should_send_digest(scheduled_time, current_user_time, schedule['days']):
                    await self._send_digest_to_user(user_id)
                    
            except ValueError as e:
                logger.error(f"Ошибка парсинга времени для пользователя {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка при проверке дайджеста пользователя {user_id}: {e}")
    
    def _should_send_digest(self, scheduled_time, current_time, days) -> bool:
        """Определяет, нужно ли отправить дайджест."""
        # Если дни не указаны, отправляем каждый день
        if not days:
            return True
        
        # Получаем текущий день недели
        current_day = datetime.now().strftime('%A').lower()
        
        # Проверяем, включен ли текущий день
        if current_day not in [day.lower() for day in days]:
            return False
        
        # Проверяем время (с допуском в 5 минут)
        time_diff = abs((current_time.hour * 60 + current_time.minute) - 
                       (scheduled_time.hour * 60 + scheduled_time.minute))
        
        return time_diff <= 5
    
    async def _send_digest_to_user(self, user_id: int):
        """Отправляет дайджест пользователю."""
        try:
            # Получаем настройки пользователя
            channels = get_user_channels(user_id)
            if not channels:
                return
            
            include_keys, exclude_keys = get_user_filters(user_id)
            per_batch = get_user_news_count(user_id)
            
            # Собираем посты со всех каналов
            all_posts = []
            for channel_url in channels[:5]:
                try:
                    posts = self.tg_parser.parse_channel(channel_url, 20)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Ошибка при парсинге канала {channel_url}: {e}")
                    continue
            
            if not all_posts:
                return
            
            # Сортируем по дате и применяем фильтры
            all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
            filtered_posts = apply_filters(all_posts, include_keys, exclude_keys)
            
            # Берем топ посты для дайджеста
            digest_posts = filtered_posts[:per_batch * 2]
            
            if not digest_posts:
                return
            
            # Отправляем заголовок дайджеста
            await self.bot.send_message(
                user_id,
                f"📰 <b>Ежедневный дайджест</b>\n\n"
                f"Найдено {len(digest_posts)} интересных постов для вас",
                parse_mode="HTML"
            )
            
            # Отправляем посты с задержкой
            for i, post in enumerate(digest_posts):
                try:
                    title = clean_html(post.get('title', 'Без заголовка'))
                    text = clean_html(post.get('text', ''))
                    
                    if len(text) > 300:
                        text = text[:300] + "..."
                    
                    caption = f"📢 <b>{title}</b>\n\n"
                    if text:
                        caption += f"💬 {text}\n\n"
                    caption += f"📍 Канал: @{post.get('channel', 'Неизвестный канал')}\n"
                    caption += f"🔗 <a href='{post.get('link', '')}'>Читать далее</a>"
                    
                    if post.get('image_url'):
                        try:
                            await self.bot.send_photo(
                                user_id,
                                photo=post['image_url'],
                                caption=caption,
                                parse_mode="HTML"
                            )
                        except Exception:
                            await self.bot.send_message(user_id, caption, parse_mode="HTML")
                    else:
                        await self.bot.send_message(user_id, caption, parse_mode="HTML")
                    
                    # Задержка между постами
                    if i < len(digest_posts) - 1:
                        await asyncio.sleep(1.5)
                        
                except Exception as e:
                    logger.error(f"Ошибка при отправке поста в дайджесте: {e}")
                    continue
            
            # Отправляем итоговое сообщение
            await self.bot.send_message(
                user_id,
                f"✅ Дайджест завершен! Показано {len(digest_posts)} постов.\n\n"
                f"Используйте /digest для получения дополнительных постов.",
                parse_mode="HTML"
            )
            
            # Обновляем статистику
            update_user_activity(user_id)
            
            logger.info(f"Дайджест отправлен пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке дайджеста пользователю {user_id}: {e}")
    
    async def _cleanup_old_data(self):
        """Очищает старые данные."""
        try:
            # Здесь можно добавить очистку старых уведомлений, истории просмотров и т.д.
            logger.info("Очистка старых данных завершена")
        except Exception as e:
            logger.error(f"Ошибка при очистке данных: {e}")
    
    async def send_instant_digest(self, user_id: int, custom_channels: List[str] = None):
        """Отправляет мгновенный дайджест пользователю."""
        try:
            channels = custom_channels or get_user_channels(user_id)
            if not channels:
                await self.bot.send_message(user_id, "У вас нет добавленных каналов для дайджеста.")
                return
            
            include_keys, exclude_keys = get_user_filters(user_id)
            per_batch = get_user_news_count(user_id)
            
            # Собираем посты
            all_posts = []
            for channel_url in channels[:5]:
                try:
                    posts = self.tg_parser.parse_channel(channel_url, 30)
                    all_posts.extend(posts)
                except Exception:
                    continue
            
            if not all_posts:
                await self.bot.send_message(user_id, "Не удалось получить посты для дайджеста.")
                return
            
            # Фильтруем и сортируем
            all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
            filtered_posts = apply_filters(all_posts, include_keys, exclude_keys)[:per_batch * 3]
            
            if not filtered_posts:
                await self.bot.send_message(user_id, "По текущим фильтрам не найдено постов для дайджеста.")
                return
            
            await self.bot.send_message(
                user_id,
                f"📰 <b>Мгновенный дайджест</b>\n\n"
                f"Найдено {len(filtered_posts)} постов",
                parse_mode="HTML"
            )
            
            # Отправляем посты
            for i, post in enumerate(filtered_posts):
                try:
                    title = clean_html(post.get('title', 'Без заголовка'))
                    text = clean_html(post.get('text', ''))
                    
                    if len(text) > 300:
                        text = text[:300] + "..."
                    
                    caption = f"📢 <b>{title}</b>\n\n"
                    if text:
                        caption += f"💬 {text}\n\n"
                    caption += f"📍 Канал: @{post.get('channel', 'Неизвестный канал')}\n"
                    caption += f"🔗 <a href='{post.get('link', '')}'>Читать далее</a>"
                    
                    if post.get('image_url'):
                        try:
                            await self.bot.send_photo(
                                user_id,
                                photo=post['image_url'],
                                caption=caption,
                                parse_mode="HTML"
                            )
                        except Exception:
                            await self.bot.send_message(user_id, caption, parse_mode="HTML")
                    else:
                        await self.bot.send_message(user_id, caption, parse_mode="HTML")
                    
                    if i < len(filtered_posts) - 1:
                        await asyncio.sleep(1.2)
                        
                except Exception as e:
                    logger.error(f"Ошибка при отправке поста: {e}")
                    continue
            
            await self.bot.send_message(
                user_id,
                f"✅ Дайджест завершен! Показано {len(filtered_posts)} постов.",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при отправке мгновенного дайджеста: {e}")
            await self.bot.send_message(user_id, "❌ Произошла ошибка при формировании дайджеста.")
    
    async def send_notification(self, user_id: int, notification_type: str, title: str, message: str, data: str = None):
        """Отправляет уведомление пользователю."""
        try:
            # Сохраняем в БД
            add_notification(user_id, notification_type, title, message, data)
            
            # Отправляем через бота
            await self.bot.send_message(
                user_id,
                f"🔔 <b>{title}</b>\n\n{message}",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
    
    async def send_important_news_notification(self, user_id: int, post: Dict, keywords: List[str]):
        """Отправляет уведомление о важной новости."""
        try:
            title = clean_html(post.get('title', 'Важная новость'))
            source = post.get('channel', 'Неизвестный канал')
            matched_keywords = [kw for kw in keywords if kw.lower() in title.lower()]
            
            message = (
                f"🚨 <b>Важная новость по вашим интересам!</b>\n\n"
                f"<b>{title}</b>\n\n"
                f"📍 Источник: @{source}\n"
                f"🔑 Ключевые слова: {', '.join(matched_keywords)}\n\n"
                f"🔗 <a href='{post.get('link', '')}'>Читать далее</a>"
            )
            
            await self.send_notification(
                user_id,
                'important_news',
                'Важная новость',
                message,
                post.get('link', '')
            )
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о важной новости: {e}")
