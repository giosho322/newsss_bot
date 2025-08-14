#!/usr/bin/env python3
"""
Планировщик для автоматических дайджестов
Упрощенная версия
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database.db import (
    get_digest_schedule, set_digest_schedule, get_user_channels,
    get_user_news_count, get_active_users
)
from parsers.telegram_parser import TelegramParser

logger = logging.getLogger(__name__)

class NewsScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.bot = None
        self.parser = TelegramParser()
        logger.info("Планировщик новостей инициализирован")

    async def setup_all_schedules(self):
        """Настраивает расписания для всех активных пользователей"""
        try:
            # Получаем всех активных пользователей
            users = get_active_users()
            
            for user_id in users:
                # Получаем настройки дайджеста пользователя
                schedule = get_digest_schedule(user_id)
                
                if schedule and schedule.get('enabled', False):
                    # Добавляем задачу в планировщик
                    time_str = schedule.get('time', '09:00')
                    days = schedule.get('days', [0, 1, 2, 3, 4, 5, 6])  # Все дни по умолчанию
                    
                    # Создаем cron триггер
                    hour, minute = map(int, time_str.split(':'))
                    
                    # Добавляем задачу для каждого дня недели
                    for day in days:
                        job_id = f"digest_{user_id}_{day}"
                        self.scheduler.add_job(
                            func=self.send_digest,
                            trigger=CronTrigger(day_of_week=day, hour=hour, minute=minute),
                            args=[user_id],
                            id=job_id,
                            replace_existing=True
                        )
                    
                    logger.info(f"Настроен дайджест для пользователя {user_id} в {time_str}")
            
            # Запускаем планировщик
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Планировщик новостей запущен")
            
        except Exception as e:
            logger.error(f"Ошибка при настройке расписаний: {e}")

    async def send_digest(self, user_id: int) -> None:
        """Отправляет дайджест новостей пользователю"""
        try:
            if not self.bot:
                logger.error("Бот не инициализирован для отправки дайджеста")
                return
            
            # Получаем настройки пользователя
            channels = get_user_channels(user_id)
            news_count = get_user_news_count(user_id)
            
            if not channels:
                logger.warning(f"Нет каналов для дайджеста у пользователя {user_id}")
                return
            
            # Парсим новости с каналов
            all_posts = []
            for channel_url in channels[:5]:  # Берем первые 5 каналов
                try:
                    posts = self.parser.parse_channel(channel_url, news_count)
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Ошибка при парсинге канала {channel_url}: {e}")
                    continue
            
            if not all_posts:
                logger.warning(f"Нет новостей для дайджеста у пользователя {user_id}")
                return
            
            # Сортируем по дате
            all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
            posts_to_send = all_posts[:news_count]
            
            # Формируем сообщение дайджеста
            message = "📰 <b>Ваш ежедневный дайджест:</b>\n\n"
            
            for idx, post in enumerate(posts_to_send, 1):
                title = post.get('title', 'Без заголовка')
                channel = post.get('channel', 'Неизвестный канал')
                message += f"{idx}. <b>{title}</b>\n"
                message += f"   📺 {channel}\n\n"
            
            # Отправляем дайджест
            await self.bot.send_message(
                user_id, 
                message, 
                parse_mode="HTML"
            )
            
            logger.info(f"Отправлен дайджест пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке дайджеста: {e}")

    async def send_instant_digest(self, user_id: int) -> None:
        """Отправляет мгновенный дайджест"""
        await self.send_digest(user_id)

    def set_digest_schedule(self, user_id: int, time_str: str, days: list, enable: bool = True):
        """Устанавливает расписание дайджеста для пользователя"""
        try:
            # Сохраняем в базу данных
            set_digest_schedule(user_id, time_str, days, enable)
            
            if enable:
                # Добавляем задачу в планировщик
                hour, minute = map(int, time_str.split(':'))
                
                for day in days:
                    job_id = f"digest_{user_id}_{day}"
                    self.scheduler.add_job(
                        func=self.send_digest,
                        trigger=CronTrigger(day_of_week=day, hour=hour, minute=minute),
                        args=[user_id],
                        id=job_id,
                        replace_existing=True
                    )
                
                logger.info(f"Установлен дайджест для пользователя {user_id} в {time_str}")
            else:
                # Удаляем задачи из планировщика
                for day in days:
                    job_id = f"digest_{user_id}_{day}"
                    try:
                        self.scheduler.remove_job(job_id)
                    except:
                        pass
                
                logger.info(f"Отключен дайджест для пользователя {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка при установке расписания дайджеста: {e}")

    def stop(self):
        """Останавливает планировщик"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Планировщик новостей остановлен")