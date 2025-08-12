from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📰 Последние новости")],
            [KeyboardButton(text="🔍 Поиск по темам")],
            [KeyboardButton(text="🎯 Поиск по запросу")],
            [KeyboardButton(text="📊 Топ за сегодня")],
            [KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="📈 Статистика")],
            [KeyboardButton(text="🔔 Уведомления")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )

def get_themes_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🐍 Python", callback_data="theme_python")],
            [InlineKeyboardButton(text="⚡ JavaScript", callback_data="theme_js")],
            [InlineKeyboardButton(text="🤖 AI/ML", callback_data="theme_ai")],
            [InlineKeyboardButton(text="🌐 Веб-разработка", callback_data="theme_web")],
        ]
    )

def get_news_buttons(url: str, news_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть", url=url)],
            [InlineKeyboardButton(text="📝 Кратко", callback_data=f"tldr_{news_id}")],
            [InlineKeyboardButton(text="📖 Полная статья", callback_data=f"full_{news_id}")],
            [InlineKeyboardButton(text="💾 Сохранить", callback_data=f"save_{news_id}")],
            [InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{news_id}")],
            [InlineKeyboardButton(text="💬 Комментировать", callback_data=f"comment_{news_id}")],
        ]
    )

def get_full_article_buttons(url: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть оригинал", url=url)],
            [InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main_from_article")],
        ]
    )

def get_top_news_buttons(more_callback_data: str = "more_top_news"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Еще новости", callback_data=more_callback_data)],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_top_news_initial_buttons():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁️ Смотреть топ за сегодня", callback_data="view_top_today")],
            [InlineKeyboardButton(text="⚙️ Изменить каналы", callback_data="manage_channels")],
            [InlineKeyboardButton(text="📅 Настроить расписание", callback_data="schedule_digest")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_manage_channels_buttons(channels: list, page: int = 0):
    buttons = []
    
    # Показываем каналы на текущей странице
    start_idx = page * 5
    end_idx = start_idx + 5
    page_channels = channels[start_idx:end_idx]
    
    for i, channel in enumerate(page_channels, start_idx):
        channel_name = channel.split('/')[-1] if '/' in channel else channel
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {channel_name}", 
                callback_data=f"delete_channel_{i}"
            )
        ])
    
    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"channels_page_{page-1}"))
    
    if end_idx < len(channels):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"channels_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Основные кнопки
    buttons.extend([
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_channel_operation")],
        ]
    )

def get_settings_buttons(news_count: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data="settings_decrease"),
                InlineKeyboardButton(text=f"Размер пачки: {news_count}", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data="settings_increase"),
            ],
            [InlineKeyboardButton(text="🧩 Включающие фильтры", callback_data="settings_edit_include")],
            [InlineKeyboardButton(text="🚫 Исключающие фильтры", callback_data="settings_edit_exclude")],
            [InlineKeyboardButton(text="🧹 Очистить фильтры", callback_data="settings_clear_filters")],
            [InlineKeyboardButton(text="📅 Расписание дайджестов", callback_data="schedule_digest")],
            [InlineKeyboardButton(text="🎨 Тема оформления", callback_data="settings_theme")],
            [InlineKeyboardButton(text="🔔 Настройки уведомлений", callback_data="settings_notifications")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_post_action_buttons(url: str, news_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть", url=url)],
            [InlineKeyboardButton(text="📝 Кратко", callback_data=f"tldr_{news_id}")],
        ]
    )

def get_digest_schedule_buttons():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Установить время", callback_data="digest_set_time")],
            [InlineKeyboardButton(text="📅 Выбрать дни", callback_data="digest_set_days")],
            [InlineKeyboardButton(text="✅ Включить автодайджест", callback_data="digest_enable")],
            [InlineKeyboardButton(text="❌ Отключить автодайджест", callback_data="digest_disable")],
            [InlineKeyboardButton(text="🔔 Тест уведомления", callback_data="digest_test")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_time_selection_buttons():
    """Клавиатура для выбора времени дайджеста"""
    buttons = []
    for hour in range(6, 23, 2):  # С 6:00 до 22:00 каждые 2 часа
        for minute in [0, 30]:
            time_str = f"{hour:02d}:{minute:02d}"
            buttons.append([InlineKeyboardButton(text=time_str, callback_data=f"time_{time_str}")])
    
    buttons.append([InlineKeyboardButton(text="🏠 Назад", callback_data="schedule_digest")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_days_selection_buttons():
    """Клавиатура для выбора дней недели"""
    days = [
        ("Понедельник", "monday"),
        ("Вторник", "tuesday"),
        ("Среда", "wednesday"),
        ("Четверг", "thursday"),
        ("Пятница", "friday"),
        ("Суббота", "saturday"),
        ("Воскресенье", "sunday"),
    ]
    
    buttons = []
    for day_name, day_code in days:
        buttons.append([
            InlineKeyboardButton(text=f"☑️ {day_name}", callback_data=f"day_{day_code}")
        ])
    
    buttons.extend([
        [InlineKeyboardButton(text="✅ Все дни", callback_data="day_all")],
        [InlineKeyboardButton(text="🏠 Назад", callback_data="schedule_digest")],
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_theme_selection_buttons():
    """Клавиатура для выбора темы оформления"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="☀️ Светлая тема", callback_data="theme_light")],
            [InlineKeyboardButton(text="🌙 Темная тема", callback_data="theme_dark")],
            [InlineKeyboardButton(text="🎨 Авто (по времени)", callback_data="theme_auto")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="settings_theme")],
        ]
    )

def get_notification_settings_buttons():
    """Клавиатура для настроек уведомлений"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Включить уведомления", callback_data="notif_enable")],
            [InlineKeyboardButton(text="🔕 Отключить уведомления", callback_data="notif_disable")],
            [InlineKeyboardButton(text="🚨 Важные новости", callback_data="notif_important")],
            [InlineKeyboardButton(text="📰 Ежедневные дайджесты", callback_data="notif_digest")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="settings_notifications")],
        ]
    )

def get_statistics_buttons():
    """Клавиатура для статистики"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="stats_general")],
            [InlineKeyboardButton(text="📈 Активность по дням", callback_data="stats_activity")],
            [InlineKeyboardButton(text="🏷️ Популярные теги", callback_data="stats_tags")],
            [InlineKeyboardButton(text="📱 Популярные источники", callback_data="stats_sources")],
            [InlineKeyboardButton(text="📤 Экспорт данных", callback_data="stats_export")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_rating_buttons(post_id: str):
    """Клавиатура для оценки поста"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1⭐", callback_data=f"rate_{post_id}_1"),
                InlineKeyboardButton(text="2⭐", callback_data=f"rate_{post_id}_2"),
                InlineKeyboardButton(text="3⭐", callback_data=f"rate_{post_id}_3"),
                InlineKeyboardButton(text="4⭐", callback_data=f"rate_{post_id}_4"),
                InlineKeyboardButton(text="5⭐", callback_data=f"rate_{post_id}_5"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="rate_cancel")],
        ]
    )

def get_comment_buttons(post_id: str):
    """Клавиатура для комментариев"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Добавить комментарий", callback_data=f"comment_add_{post_id}")],
            [InlineKeyboardButton(text="👁️ Показать комментарии", callback_data=f"comment_show_{post_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="comment_cancel")],
        ]
    )

def get_recommendations_buttons():
    """Клавиатура для рекомендаций"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Получить рекомендации", callback_data="recs_get")],
            [InlineKeyboardButton(text="⚙️ Настройки рекомендаций", callback_data="recs_settings")],
            [InlineKeyboardButton(text="📊 История рекомендаций", callback_data="recs_history")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_export_format_buttons():
    """Клавиатура для выбора формата экспорта"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Markdown", callback_data="export_md")],
            [InlineKeyboardButton(text="📊 CSV", callback_data="export_csv")],
            [InlineKeyboardButton(text="🔗 JSON", callback_data="export_json")],
            [InlineKeyboardButton(text="📋 Текст", callback_data="export_txt")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="stats_export")],
        ]
    )

def get_search_advanced_buttons():
    """Клавиатура для расширенного поиска"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Поиск по дате", callback_data="search_date")],
            [InlineKeyboardButton(text="👤 Поиск по автору", callback_data="search_author")],
            [InlineKeyboardButton(text="🏷️ Поиск по тегам", callback_data="search_tags")],
            [InlineKeyboardButton(text="🔍 Комбинированный поиск", callback_data="search_combined")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )

def get_archive_buttons():
    """Клавиатура для архива"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Просмотр архива", callback_data="archive_browse")],
            [InlineKeyboardButton(text="🔍 Поиск в архиве", callback_data="archive_search")],
            [InlineKeyboardButton(text="📤 Экспорт архива", callback_data="archive_export")],
            [InlineKeyboardButton(text="🧹 Очистить архив", callback_data="archive_clear")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
        ]
    )