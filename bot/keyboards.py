#!/usr/bin/env python3
"""
Клавиатуры для бота
Возвращены кнопки основного меню и действия с постами
"""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from database.db import get_or_create_link_token

def get_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню (reply-клавиатура)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📰 Последние новости"), KeyboardButton(text="📊 Топ за сегодня")],
            [KeyboardButton(text="🔍 Поиск по запросу"), KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="📈 Статистика"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-меню (для сообщений)"""
    keyboard = [
        [InlineKeyboardButton(text="📰 Топ новостей", callback_data="top_news")],
        [InlineKeyboardButton(text="📅 Получить дайджест", callback_data="digest")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📖 Справка", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = [
        [InlineKeyboardButton(text="📺 Каналы", callback_data="settings_channels")],
        [InlineKeyboardButton(text="📊 Количество новостей", callback_data="settings_news_count")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_channels_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура каналов"""
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_digest_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура дайджеста"""
    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="digest")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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

def get_help_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура справки"""
    keyboard = [
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_post_keyboard(link: str, post_id: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура под постом: открыть, кратко, полная, сохранить.
    Для callback используем короткий токен, чтобы не превышать лимит 64 байта.
    """
    rows = [[InlineKeyboardButton(text="🔗 Открыть", url=link)]]
    token = post_id or get_or_create_link_token(link)
    if token:
        rows.append([
            InlineKeyboardButton(text="📝 Кратко", callback_data=f"tldr:{token}"),
            InlineKeyboardButton(text="📖 Полная", callback_data=f"full:{token}"),
        ])
        rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data=f"save:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_top_news_buttons(more_callback_data: str = "more_top_news:1") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Еще новости", callback_data=more_callback_data)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )