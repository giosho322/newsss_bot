#!/usr/bin/env python3
"""
Админские функции для управления ботом
Упрощенная версия
"""

import logging
from typing import List, Optional
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_active_users, add_user, get_user, get_total_users, get_all_user_ids

logger = logging.getLogger(__name__)

# ID администраторов (замените на свои)
ADMIN_IDS = [1203425573]

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

async def send_message_to_all_users(bot: Bot, message_text: str, admin_id: int) -> dict:
    """Отправляет сообщение всем пользователям"""
    if not is_admin(admin_id):
        return {"success": False, "error": "Недостаточно прав"}
    
    try:
        # Рассылка всем активным пользователям (is_active=1), а не только по последней активности
        users = get_all_user_ids(only_active=False)
        success_count = 0
        error_count = 0
        
        for user_id in users:
            try:
                await bot.send_message(user_id, message_text)
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                error_count += 1
        
        return {
            "success": True,
            "sent": success_count,
            "errors": error_count,
            "total": len(users)
        }
        
    except Exception as e:
        logger.error(f"Ошибка при массовой рассылке: {e}")
        return {"success": False, "error": str(e)}

async def send_message_to_user(bot: Bot, target_user_id: int, message_text: str, admin_id: int) -> dict:
    """Отправляет сообщение конкретному пользователю"""
    if not is_admin(admin_id):
        return {"success": False, "error": "Недостаточно прав"}
    
    try:
        await bot.send_message(target_user_id, message_text)
        return {"success": True, "sent": 1}
        
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {target_user_id}: {e}")
        return {"success": False, "error": str(e)}

async def get_users_statistics(admin_id: int) -> dict:
    """Получает статистику пользователей"""
    if not is_admin(admin_id):
        return {"success": False, "error": "Недостаточно прав"}
    
    try:
        active = get_active_users()
        stats = {
            "total_users": get_total_users(),
            "active_users": len(active),
            "new_users_today": 0,
            "total_views": 0,
            "total_digests": 0,
        }
        
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return {"success": False, "error": str(e)}

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура админ-панели"""
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура рассылки"""
    keyboard = [
        [InlineKeyboardButton(text="📤 Отправить всем", callback_data="admin_broadcast_all")],
        [InlineKeyboardButton(text="👤 Отправить пользователю", callback_data="admin_broadcast_user")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_send_user_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отправки пользователю"""
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
