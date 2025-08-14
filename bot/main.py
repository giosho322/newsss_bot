#!/usr/bin/env python3
"""
Telegram News Bot (возвращены: последние новости, поиск, избранное, статистика, админ-панель)
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, BufferedInputFile
from aiogram import types
import aiohttp
from bs4 import BeautifulSoup

from .config import BOT_TOKEN, TELEGRAM_CHANNELS
from .keyboards import (
    get_main_keyboard,
    get_main_menu,
    get_settings_keyboard,
    get_channels_keyboard,
    get_digest_keyboard,
    get_admin_keyboard,
    get_post_keyboard,
    get_top_news_buttons,
)
from .scheduler import NewsScheduler
from .admin import is_admin, get_users_statistics, send_message_to_all_users, send_message_to_user

from database.db import (
    init_db,
    add_user,
    get_user_channels,
    get_user_news_count,
    set_user_news_count,
    get_active_users,
    save_news,
    get_favorites,
    add_search_query,
    get_user_stats,
    add_view_history,
    get_url_by_token,
)
from parsers.telegram_parser import TelegramParser
from parsers.base_parser import BaseParser
from parsers.habr_parser import HabrParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
parser = TelegramParser()

# Флаги ожидания ввода для рассылки
from typing import Set
BROADCAST_ALL_WAITING: Set[int] = set()
BROADCAST_USER_WAITING: Set[int] = set()

# Навигация по новостям для каждого пользователя
from typing import Dict, List
NEWS_NAVIGATION: Dict[int, Dict] = {}  # user_id -> {posts, current_index, message_id, chat_id}

# Добавляем защиту от спама для навигации
NAVIGATION_COOLDOWN = {}  # user_id -> timestamp

MENU_TEXTS = {
    "📰 Последние новости",
    "📊 Топ за сегодня",
    "🔍 Поиск по запросу",
    "⭐ Избранное",
    "📈 Статистика",
    "⚙️ Настройки",
}

class NewsNavigator:
    def __init__(self, posts: List[Dict], start_index: int = 0):
        self.posts = posts
        self.current_index = start_index
        self.current_view_mode = "normal"  # normal, tldr, full
        self.post_contents = {}  # Словарь для хранения контента каждого поста: {post_index: {"tldr": "...", "full": "..."}}
        self.message_id = None             # ID сообщения для редактирования
        
    def get_current_post(self) -> Optional[Dict]:
        """Возвращает текущий пост"""
        if 0 <= self.current_index < len(self.posts):
            return self.posts[self.current_index]
        return None
    
    def has_next(self) -> bool:
        """Проверяет, есть ли следующая новость"""
        return self.current_index < len(self.posts) - 1
    
    def has_prev(self) -> bool:
        """Проверяет, есть ли предыдущая новость"""
        return self.current_index > 0
    
    def next_post(self):
        """Переходит к следующей новости"""
        if self.has_next():
            self.current_index += 1
            # Сбрасываем режим просмотра при переходе к новой новости
            self.current_view_mode = "normal"
            return True
        return False
    
    def prev_post(self):
        """Переходит к предыдущей новости"""
        if self.has_prev():
            self.current_index -= 1
            # Сбрасываем режим просмотра при переходе к новой новости
            self.current_view_mode = "normal"
            return True
        return False
    
    def set_view_mode(self, mode: str):
        """Устанавливает режим просмотра"""
        self.current_view_mode = mode
    
    def get_post_content(self, content_type: str) -> str:
        """Получает контент для текущего поста"""
        if self.current_index not in self.post_contents:
            return ""
        return self.post_contents[self.current_index].get(content_type, "")
    
    def set_post_content(self, content_type: str, content: str):
        """Устанавливает контент для текущего поста"""
        if self.current_index not in self.post_contents:
            self.post_contents[self.current_index] = {}
        self.post_contents[self.current_index][content_type] = content
    
    def get_navigation_text(self) -> str:
        """Возвращает текст для навигации"""
        post = self.get_current_post()
        if not post:
            return "Новость не найдена"
        
        title = post.get("title", "Без заголовка")
        source = post.get("source", "")
        link = post.get("link", "")
        
        # Логируем для отладки источника
        logger.info(f"DEBUG: Пост '{title[:50]}...' - source: '{source}', link: '{link}'")
        
        # Формируем основной текст
        text = f"<b>{title}</b>\n\n"
        
        if source:
            # Определяем, является ли это Telegram постом
            is_telegram = (
                "t.me" in link or 
                "cdn4.telesco.pe" in str(post.get("image_url", "")) or
                (source and source.lower() not in ["habr", "habr.com", "habr.ru"])
            )
            
            logger.info(f"DEBUG: is_telegram={is_telegram} для источника '{source}'")
            
            if is_telegram:
                # Исправляем источник для старых новостей
                if source == "telegram" and "t.me" in link:
                    # Извлекаем название канала из ссылки
                    try:
                        channel_name = link.split('/')[-2] if '/' in link else 'telegram'
                        # Убираем подчеркивания и приводим к читаемому виду
                        if channel_name == 'vedomosti':
                            display_name = 'Ведомости'
                        elif channel_name == 'rbc_news':
                            display_name = 'РБК'
                        elif channel_name == 'mk_ru':
                            display_name = 'МК'
                        elif channel_name == 'izvestia_ru':
                            display_name = 'Известия'
                        elif channel_name == 'rbcrostov':
                            display_name = 'РБК Ростов'
                        else:
                            display_name = channel_name.replace('_', ' ').title()
                        text += f"📺 Канал: {display_name}\n"
                    except:
                        text += f"📺 Канал: telegram\n"
                elif source:
                    # Для Telegram показываем название канала
                    text += f"📺 Канал: {source}\n"
                else:
                    text += f"📺 Канал: telegram\n"
            elif source:
                # Для других источников показываем домен
                text += f"📰 Источник: {source}\n"
        
        if link:
            text += f"🔗 <a href='{link}'>Читать полностью</a>\n\n"
        
        # Добавляем контент в зависимости от режима просмотра
        if self.current_view_mode == "tldr" and self.get_post_content("tldr"):
            text += f"<b>📝 Краткое содержание:</b>\n{self.get_post_content('tldr')}\n\n"
        elif self.current_view_mode == "full" and self.get_post_content("full"):
            # Ограничиваем длину полной статьи
            full_content = self.get_post_content('full')[:2000] + "..." if len(self.get_post_content('full')) > 2000 else self.get_post_content('full')
            text += f"<b>📖 Полная статья:</b>\n{full_content}\n\n"
        
        # Добавляем информацию о навигации
        text += f"📄 {self.current_index + 1} из {len(self.posts)}"
        
        return text
    
    def get_navigation_keyboard(self) -> InlineKeyboardMarkup:
        """Возвращает клавиатуру навигации в зависимости от режима просмотра"""
        keyboard = []
        
        # Кнопки навигации
        nav_row = []
        if self.current_index > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="news_prev"))
        if self.current_index < len(self.posts) - 1:
            nav_row.append(InlineKeyboardButton(text="Следующая новость ➡️", callback_data="news_next"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        # Кнопки режима просмотра - всегда показываем
        if self.current_view_mode == "normal":
            # В обычном режиме показываем кнопки для переключения
            keyboard.append([InlineKeyboardButton(text="📝 Кратко", callback_data="view_tldr")])
            keyboard.append([InlineKeyboardButton(text="📖 Полная", callback_data="view_full")])
        elif self.current_view_mode == "tldr":
            # В режиме краткого содержания показываем кнопки для переключения
            keyboard.append([InlineKeyboardButton(text="📖 Полная", callback_data="view_full")])
            keyboard.append([InlineKeyboardButton(text="🔙 Обычный вид", callback_data="view_normal")])
        elif self.current_view_mode == "full":
            # В режиме полной статьи показываем кнопки для переключения
            keyboard.append([InlineKeyboardButton(text="📝 Кратко", callback_data="view_tldr")])
            keyboard.append([InlineKeyboardButton(text="🔙 Обычный вид", callback_data="view_normal")])
        
        # Кнопки действий
        action_row = []
        current_post = self.get_current_post()
        if current_post:
            # Проверяем, что у нас есть валидный пост
            post_id = str(hash(current_post.get('link', '')))
            if post_id and post_id != '0':  # Убеждаемся, что ID не пустой
                action_row.append(InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite_{post_id}"))
        
        action_row.append(InlineKeyboardButton(text="🔙 Главное меню", callback_data="news_exit"))
        
        if action_row:
            keyboard.append(action_row)
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    def get_media_files(self) -> Dict:
        """Возвращает медиафайлы для текущего поста"""
        post = self.get_current_post()
        if not post:
            return {}
        
        media = {}
        
        # Изображения
        if post.get("image_url"):
            media["photo"] = post.get("image_url")
        
        # Видео
        if post.get("video_url"):
            media["video"] = post.get("video_url")
        
        # Анимации/GIF
        if post.get("animation_url"):
            media["animation"] = post.get("animation_url")
        
        # Логируем для отладки
        logger.info(f"Извлекаем медиа из поста: {post.get('title', 'Без заголовка')}")
        logger.info(f"  Доступные медиа: image_url={post.get('image_url')}, video_url={post.get('video_url')}, animation_url={post.get('animation_url')}")
        logger.info(f"  Итоговый media dict: {media}")
        
        return media
    
    def needs_more_posts(self) -> bool:
        """Проверяет, нужно ли загрузить больше новостей"""
        return self.current_index >= len(self.posts) - 3  # Загружаем когда остается 3 поста

async def _try_send_photo(message: Message, image_url: str, caption: str, reply_markup=None) -> bool:
    if not image_url:
        return False
    try:
        await message.answer_photo(photo=image_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=10) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file = BufferedInputFile(content, filename="image.jpg")
                    await message.answer_photo(photo=file, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
                    return True
    except Exception:
        return False
    return False

async def _try_send_video(message: Message, video_url: str, caption: str, reply_markup=None) -> bool:
    if not video_url:
        return False
    try:
        await message.answer_video(video=video_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=15) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file = BufferedInputFile(content, filename="video.mp4")
                    await message.answer_video(video=file, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
                    return True
    except Exception:
        return False
    return False

async def _try_send_animation(message: Message, animation_url: str, caption: str, reply_markup=None) -> bool:
    if not animation_url:
        return False
    try:
        await message.answer_animation(animation=animation_url, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(animation_url, timeout=15) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    file = BufferedInputFile(content, filename="animation.gif")
                    await message.answer_animation(animation=file, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
                    return True
    except Exception:
        return False
    return False

# ===== Helpers =====

def _to_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return date.today()

async def _collect_posts(days: int) -> List[Dict[str, Any]]:
    """Собирает посты с каналов за days дней, сортирует по популярности (views)."""
    threshold = date.today() - timedelta(days=days - 1)
    all_posts: List[Dict[str, Any]] = []
    
    logger.info(f"Начинаем сбор постов за {days} дней...")
    
    for channel_url in TELEGRAM_CHANNELS:
        try:
            logger.info(f"Парсим канал: {channel_url}")
            posts = parser.parse_channel(channel_url, limit=60)
            logger.info(f"Получено {len(posts)} постов с канала {channel_url}")
            
            for p in posts:
                p_date = _to_date(p.get("date", ""))
                if p_date >= threshold:
                    # Правильно устанавливаем источник на основе URL канала
                    if "vedomosti" in channel_url:
                        p['source'] = 'vedomosti'
                    elif "rbc_news" in channel_url:
                        p['source'] = 'rbc_news'
                    elif "mk_ru" in channel_url:
                        p['source'] = 'mk_ru'
                    elif "izvestia_ru" in channel_url:
                        p['source'] = 'izvestia_ru'
                    else:
                        # Извлекаем название канала из URL
                        channel_name = channel_url.split('/')[-1] if channel_url.endswith('/') else channel_url.split('/')[-1]
                        p['source'] = channel_name
                    
                    # Логируем медиафайлы для отладки
                    if p.get("image_url") or p.get("video_url") or p.get("animation_url"):
                        logger.info(f"Найден пост с медиа: {p.get('title', 'Без заголовка')}")
                        logger.info(f"  image_url: {p.get('image_url')}")
                        logger.info(f"  video_url: {p.get('video_url')}")
                        logger.info(f"  animation_url: {p.get('animation_url')}")
                        logger.info(f"  source: {p.get('source', 'НЕТ')}")
                    else:
                        logger.debug(f"Пост без медиа: {p.get('title', 'Без заголовка')}")
                        logger.debug(f"  source: {p.get('source', 'НЕТ')}")
                    
                    all_posts.append(p)
        except Exception as e:
            logger.error(f"Ошибка при парсинге {channel_url}: {e}")
            continue
    
    logger.info(f"Всего собрано постов: {len(all_posts)}")
    
    # Сортируем по популярности (views), затем по дате
    all_posts.sort(key=lambda x: (x.get("views", 0), x.get("date", "")), reverse=True)
    
    # Логируем первые несколько постов для проверки
    for i, post in enumerate(all_posts[:3]):
        logger.info(f"Пост {i+1}: {post.get('title', 'Без заголовка')[:50]}...")
        logger.info(f"  Медиа: image={post.get('image_url', 'НЕТ')}, video={post.get('video_url', 'НЕТ')}, animation={post.get('animation_url', 'НЕТ')}")
        logger.info(f"  Источник: {post.get('source', 'НЕТ')}")
    
    return all_posts

# ===== Commands =====

@dp.message(Command("start"))
async def start_command(message: Message) -> None:
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Доступно: последние новости, топ, поиск, избранное, дайджест.\n\n"
        "Команды: /top, /digest, /settings, /help"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")

@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    text = (
        "📖 <b>Справка</b>\n\n"
        "/top — топ (за 1 день, сортировка по популярности)\n"
        "'Еще новости' — расширит охват на +1 день\n"
        "'Последние новости' — новые по дате\n"
        "'Поиск по запросу' — поиск по тексту/заголовку\n"
        "'⭐ Избранное' — сохраненные ссылки\n"
    )
    await message.answer(text, parse_mode="HTML")

# ===== Text menu (reply keyboard) =====

@dp.message(F.text == "📰 Последние новости")
async def latest_news(message: Message) -> None:
    await message.answer("🔄 Загружаю последние IT новости с Habr...")
    try:
        from parsers.habr_parser import HabrParser
        habr_parser = HabrParser()
        posts = habr_parser.get_latest_news(limit=15)  # Увеличиваем лимит для навигации
        
        if not posts:
            await message.answer("❌ Не удалось загрузить новости с Habr")
            return
            
        # Создаем навигатор для пользователя
        navigator = NewsNavigator(posts, 0) # Start from index 0
        NEWS_NAVIGATION[message.from_user.id] = navigator
        
        # Отправляем первую новость с медиа
        message_id = await _send_news_with_media(message, navigator)
        
        # Сохраняем ID сообщения для редактирования
        navigator.message_id = message_id
        NEWS_NAVIGATION[message.from_user.id] = navigator
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке новостей с Habr: {e}")
        await message.answer("❌ Произошла ошибка при загрузке новостей")

@dp.message(F.text == "📊 Топ за сегодня")
async def top_today(message: Message) -> None:
    await top_command(message)

# ===== Admin broadcast input handlers (должны быть до общего обработчика поиска) =====

@dp.message(lambda m: m.from_user is not None and m.from_user.id in BROADCAST_ALL_WAITING)
async def handle_broadcast_all(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    BROADCAST_ALL_WAITING.discard(message.from_user.id)
    if not text:
        await message.answer("Текст пуст. Отмена рассылки.")
        return
    result = await send_message_to_all_users(bot, text, admin_id=message.from_user.id)
    await message.answer(f"✅ Отправлено: {result.get('sent',0)} | Ошибок: {result.get('errors',0)}")

@dp.message(lambda m: m.from_user is not None and m.from_user.id in BROADCAST_USER_WAITING)
async def handle_broadcast_user(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        first_space = message.text.find(' ')
        target_id = int(message.text[:first_space])
        text = message.text[first_space+1:].strip()
    except Exception:
        await message.answer("Неверный формат. Пример: 123456789 Привет!")
        return
    BROADCAST_USER_WAITING.discard(message.from_user.id)
    result = await send_message_to_user(bot, target_id, text, admin_id=message.from_user.id)
    if result.get('success'):
        await message.answer("✅ Сообщение отправлено")
    else:
        await message.answer(f"❌ Ошибка: {result.get('error')}")

@dp.message(F.text == "🔍 Поиск по запросу")
async def ask_search_query(message: Message) -> None:
    await message.answer("Введите запрос для поиска IT новостей на Habr:")

@dp.message(lambda m: (
    isinstance(getattr(m, 'text', None), str)
    and len(m.text.strip()) >= 3
    and not m.text.startswith('/')
    and m.text.strip() not in MENU_TEXTS
    and (m.from_user is None or (m.from_user.id not in BROADCAST_ALL_WAITING and m.from_user.id not in BROADCAST_USER_WAITING))
))
async def handle_search_query(message: Message) -> None:
    query = message.text.strip()
    add_search_query(message.from_user.id, query)
    
    await message.answer(f"🔍 Ищу IT новости по запросу: <b>{query}</b>", parse_mode="HTML")
    
    try:
        from parsers.habr_parser import HabrParser
        habr_parser = HabrParser()
        found = habr_parser.search_by_query(query, limit=15)
        
        if not found:
            await message.answer("Ничего не найдено на Habr по вашему запросу")
            return
        
        # Создаем навигатор для результатов поиска
        navigator = NewsNavigator(found, 0) # Start from index 0
        NEWS_NAVIGATION[message.from_user.id] = navigator
        
        # Отправляем первый результат с медиа
        message_id = await _send_news_with_media(message, navigator)
        
        # Сохраняем ID сообщения для редактирования
        navigator.message_id = message_id
        NEWS_NAVIGATION[message.from_user.id] = navigator
            
    except Exception as e:
        logger.error(f"Ошибка при поиске на Habr: {e}")
        await message.answer("❌ Произошла ошибка при поиске")

@dp.message(F.text == "⭐ Избранное")
async def show_favorites(message: Message) -> None:
    items = get_favorites(message.from_user.id)
    if not items:
        await message.answer("Избранное пусто")
        return
    for title, url in items[:20]:
        await message.answer(f"<b>{title}</b>", parse_mode="HTML", reply_markup=get_post_keyboard(url))

@dp.message(F.text == "📈 Статистика")
async def show_stats(message: Message) -> None:
    stats = get_user_stats(message.from_user.id)
    text = (
        "📈 <b>Ваша статистика</b>\n\n"
        f"Просмотры: {stats.get('total_views', 0)}\n"
        f"Сохранено: {stats.get('total_saves', 0)}\n"
        f"Поисков: {stats.get('total_searches', 0)}\n"
    )
    await message.answer(text, parse_mode="HTML")

# Callback кнопка справки из меню
@dp.callback_query(lambda c: c.data == "help")
async def help_callback(call: CallbackQuery) -> None:
    await call.answer()
    await help_command(call.message)

@dp.message(Command("top"))
async def top_command(message: Message) -> None:
    # Топ: отправляем посты по одному (с фото, если есть), затем кнопка "Еще"
    await message.answer("🔍 Загружаю топ новости...")
    posts = await _collect_posts(days=1)
    if not posts:
        await message.answer("❌ Не удалось загрузить новости. Попробуйте позже.")
        return
    
    # Логируем медиафайлы в постах
    logger.info(f"Посты для NewsNavigator: {len(posts)}")
    for i, post in enumerate(posts[:3]):
        logger.info(f"Пост {i+1}: {post.get('title', 'Без заголовка')[:50]}...")
        logger.info(f"  Медиа: image={post.get('image_url', 'НЕТ')}, video={post.get('video_url', 'НЕТ')}, animation={post.get('animation_url', 'НЕТ')}")
        logger.info(f"  Источник: {post.get('source', 'НЕТ')}")
    
    user_limit = get_user_news_count(message.from_user.id)
    posts_to_show = posts[: max(15, user_limit)]  # Увеличиваем лимит для навигации
    
    # Создаем навигатор для топ новостей
    navigator = NewsNavigator(posts_to_show, 0) # Start from index 0
    NEWS_NAVIGATION[message.from_user.id] = navigator
    
    # Отправляем первую новость с медиа
    message_id = await _send_news_with_media(message, navigator)
    
    # Сохраняем ID сообщения для редактирования
    navigator.message_id = message_id
    NEWS_NAVIGATION[message.from_user.id] = navigator

@dp.callback_query(lambda c: c.data.startswith("top_news"))
async def top_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    await top_command(call.message)

# Убираем старый обработчик more_top_news, так как теперь используется навигация

# ===== Settings =====

@dp.callback_query(lambda c: c.data == "settings")
async def settings_callback(call: CallbackQuery) -> None:
    await call.answer()
    await show_settings(call.message)

async def show_settings(message: Message) -> None:
    uid = message.from_user.id
    news_count = get_user_news_count(uid)
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"📊 Количество новостей: <b>{news_count}</b>\n\n"
        "Выберите, что хотите изменить:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_settings_keyboard())

@dp.message(F.text == "⚙️ Настройки")
async def settings_text_handler(message: Message) -> None:
    await show_settings(message)

@dp.callback_query(lambda c: c.data == "settings_news_count")
async def settings_news_count_callback(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    current = get_user_news_count(uid)
    text = (
        "📊 <b>Количество новостей</b>\n\n"
        f"Текущее значение: <b>{current}</b>\n\n"
        "Выберите новое значение:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5", callback_data="news_count_5")],
        [InlineKeyboardButton(text="10", callback_data="news_count_10")],
        [InlineKeyboardButton(text="15", callback_data="news_count_15")],
        [InlineKeyboardButton(text="20", callback_data="news_count_20")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")],
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("news_count_"))
async def news_count_set(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    new_val = int(call.data.split("_")[-1])
    set_user_news_count(uid, new_val)
    await call.message.edit_text(
        f"✅ Количество новостей установлено: <b>{new_val}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ])
    )

@dp.callback_query(lambda c: c.data == "settings_channels")
async def settings_channels_callback(call: CallbackQuery) -> None:
    await call.answer()
    uid = call.from_user.id
    channels = get_user_channels(uid)
    text = "\n".join(["📺 <b>Ваши каналы</b>", "", *channels]) if channels else "Каналы не настроены"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_channels_keyboard())

# ===== Digest =====

@dp.callback_query(lambda c: c.data == "digest")
async def digest_callback(call: CallbackQuery) -> None:
    await call.answer()
    await send_instant_digest(call.message)

async def send_instant_digest(message: Message) -> None:
    uid = message.from_user.id
    try:
        await message.answer("📅 Подготавливаю дайджест...")
        channels = get_user_channels(uid) or TELEGRAM_CHANNELS
        limit = get_user_news_count(uid)
        all_posts: List[Dict[str, Any]] = []
        for ch in channels[:5]:
            try:
                all_posts.extend(parser.parse_channel(ch, limit=limit))
            except Exception as e:
                logger.error(f"Ошибка парсинга {ch}: {e}")
        if not all_posts:
            await message.answer("❌ Не удалось загрузить новости для дайджеста")
            return
        all_posts.sort(key=lambda x: (x.get("views", 0), x.get("date", "")), reverse=True)
        posts = all_posts[:limit]
        text = "📰 <b>Ваш дайджест:</b>\n\n"
        for i, p in enumerate(posts, 1):
            title = p.get("title", "Без заголовка")
            channel = p.get("channel", "?")
            views = p.get("views", 0)
            text += f"{i}. <b>{title}</b>\n   📺 {channel}   👁️ {views}\n\n"
        await message.answer(text, parse_mode="HTML", reply_markup=get_digest_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при отправке дайджеста: {e}")
        await message.answer("❌ Произошла ошибка при подготовке дайджеста")

# ===== Admin =====

async def show_admin_panel(message: Message) -> None:
    await message.answer("👨‍💼 <b>Админ-панель</b>\n\nВыберите действие:", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel_callback(call: CallbackQuery) -> None:
    await call.answer()
    if not is_admin(call.from_user.id):
        await call.message.answer("❌ У вас нет доступа к админ-панели")
        return
    await show_admin_panel(call.message)

@dp.message(Command("admin"))
@dp.message(Command("админ"))
async def admin_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    await show_admin_panel(message)

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats_callback(call: CallbackQuery) -> None:
    await call.answer()
    if not is_admin(call.from_user.id):
        return
    try:
        stats_resp = await get_users_statistics(call.from_user.id)
        stats = stats_resp.get("stats", {}) if isinstance(stats_resp, dict) else {}
        text = (
            "📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
            f"✅ Активных: {stats.get('active_users', 0)}\n"
        )
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]]))
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await call.message.edit_text("❌ Ошибка при получении статистики")

# Save favorite

@dp.callback_query(lambda c: c.data.startswith("save:"))
async def save_post(call: CallbackQuery) -> None:
    await call.answer()
    token = call.data.split(":", 1)[1]
    link = get_url_by_token(token) or token
    # Если сообщение с фото, берем подпись
    title = (call.message.caption or call.message.text or "Ссылка").strip()
    # Очищаем от HTML-тегов для сохранения
    soup = BeautifulSoup(title, 'html.parser')
    clean_title = soup.get_text(strip=True)
    save_news(call.from_user.id, title=clean_title, url=link)
    await call.message.answer("✅ Новость добавлена в избранное!")

# TLDR / FULL handlers (простые варианты)
@dp.callback_query(lambda c: c.data.startswith("tldr:"))
async def tldr_handler(call: CallbackQuery) -> None:
    await call.answer()
    token = call.data.split(":",1)[1]
    link = get_url_by_token(token) or token
    await _send_tldr(call.message, link)

@dp.callback_query(lambda c: c.data.startswith("full:"))
async def full_handler(call: CallbackQuery) -> None:
    await call.answer()
    token = call.data.split(":",1)[1]
    link = get_url_by_token(token) or token
    await _send_full_article(call.message, link)

# ===== Article helpers =====

def _choose_article_parser(url: str):
    u = (url or "").lower()
    if "habr.com" in u:
        return HabrParser()
    elif "t.me/" in u or "/s/" in u:
        # Для Telegram-ссылок используем BaseParser с улучшенной поддержкой Telegram
        logger.info(f"DEBUG: Выбран BaseParser для Telegram URL: {url}")
        return BaseParser()
    else:
        # Для остальных сайтов используем BaseParser
        logger.info(f"DEBUG: Выбран BaseParser для URL: {url}")
        return BaseParser()

def _is_content_relevant(title: str, content: str) -> bool:
    """Проверяет, релевантен ли контент заголовку"""
    if not title or not content:
        return False
    
    # Приводим к нижнему регистру для сравнения
    title_lower = title.lower()
    content_lower = content.lower()
    
    # Ищем ключевые слова из заголовка в контенте
    title_words = [word for word in title_lower.split() if len(word) > 3]
    
    # Проверяем, сколько ключевых слов из заголовка есть в контенте
    matches = 0
    for word in title_words[:5]:  # Берем первые 5 ключевых слов
        if word in content_lower:
            matches += 1
    
    # Если больше половины ключевых слов найдено, считаем релевантным
    relevance = matches / len(title_words) if title_words else 0
    logger.info(f"DEBUG: Релевантность контента: {relevance:.2f} ({matches}/{len(title_words)} слов)")
    
    return relevance > 0.3  # Порог релевантности 30%

def _summarize_text(text: str, max_chars: int = 300) -> str:
    """Создает краткое содержание текста"""
    if not text:
        logger.info("DEBUG: _summarize_text получил пустой текст")
        return ""
    
    logger.info(f"DEBUG: _summarize_text получил текст длиной {len(text)} символов")
    logger.info(f"DEBUG: Начало текста: {text[:100]}...")
    
    # Очищаем текст от лишних пробелов и переносов
    text = " ".join(text.split())
    
    # Если текст уже короткий, возвращаем как есть
    if len(text) <= max_chars:
        logger.info(f"DEBUG: Текст короткий, возвращаем как есть: {text}")
        return text
    
    # Разбиваем на предложения по знакам препинания
    import re
    sentences = re.split(r'[.!?]+', text)
    
    # Фильтруем пустые предложения
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Если не удалось разбить на предложения, просто обрезаем
    if not sentences:
        return text[:max_chars] + "..."
    
    # Берем первые предложения, пока не превысим лимит
    summary = ""
    for sentence in sentences:
        # Если это первое предложение и оно слишком длинное, обрезаем его
        if not summary and len(sentence) > max_chars:
            summary = sentence[:max_chars-3] + "..."
            break
        elif len(summary + sentence) <= max_chars:
            summary += sentence + ". "
        else:
            break
    
    # Убираем лишний пробел в конце и добавляем многоточие если нужно
    summary = summary.strip()
    if len(summary) < len(text):
        summary += "..."
    
    logger.info(f"DEBUG: Создано краткое содержание длиной {len(summary)} символов: {summary[:100]}...")
    
    return summary

async def _send_long_text(message: Message, text: str, header: str | None = None):
    from html import escape
    chunk_limit = 3800
    body = escape(text)
    if header:
        safe_header = escape(header)
        body = f"<b>{safe_header}</b>\n\n{body}"
    while body:
        chunk = body[:chunk_limit]
        await message.answer(chunk, parse_mode="HTML")
        body = body[chunk_limit:]

async def _send_tldr(message: Message, url: str):
    parser_obj = _choose_article_parser(url)
    res = parser_obj.parse_full_article(url)
    if not res.get("success"):
        await message.answer(f"❌ Не удалось получить кратко. Откройте ссылку: {url}")
        return
    summary = _summarize_text(res.get("content", ""))
    title = res.get("title", "Кратко")
    await _send_long_text(message, summary, header=f"📝 {title}")

async def _send_full_article(message: Message, url: str):
    parser_obj = _choose_article_parser(url)
    res = parser_obj.parse_full_article(url)
    if not res.get("success"):
        await message.answer(f"❌ Не удалось получить статью. Откройте ссылку: {url}")
        return
    content = res.get("content", "")
    title = res.get("title", "Полная статья")
    await _send_long_text(message, content, header=f"📖 {title}")

async def _send_news_with_media(message: Message, navigator: NewsNavigator, edit_message_id: int = None) -> int:
    """Отправляет новость с медиафайлами. Возвращает ID отправленного сообщения."""
    text = navigator.get_navigation_text()
    keyboard = navigator.get_navigation_keyboard()
    media = navigator.get_media_files()
    
    # Логируем для отладки
    logger.info(f"Отправляем новость с медиа: {media}")
    
    # Если есть медиа, отправляем с ним
    if media.get("video"):
        try:
            if edit_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=edit_message_id,
                    media=types.InputMediaVideo(media=media["video"], caption=text, parse_mode="HTML"),
                    reply_markup=keyboard
                )
                return edit_message_id
            else:
                sent = await message.answer_video(
                    video=media["video"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return sent.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке видео: {e}")
            # Fallback: скачиваем файл и отправляем как BufferedInputFile
            try:
                import requests
                from aiogram.types import BufferedInputFile
                
                # Устанавливаем короткий таймаут для видео
                response = requests.get(media["video"], timeout=5)
                if response.status_code == 200:
                    video_file = BufferedInputFile(response.content, filename="video.mp4")
                    
                    if edit_message_id:
                        await message.bot.edit_message_media(
                            chat_id=message.chat.id,
                            message_id=edit_message_id,
                            media=types.InputMediaVideo(media=video_file, caption=text, parse_mode="HTML"),
                            reply_markup=keyboard
                        )
                        return edit_message_id
                    else:
                        sent = await message.answer_video(
                            video=video_file,
                            caption=text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        return sent.message_id
                else:
                    logger.error(f"Не удалось скачать видео: {response.status_code}")
            except Exception as download_error:
                logger.error(f"Ошибка при скачивании видео: {download_error}")
            
            # Если все fallback не сработали, отправляем только текст
            logger.info("Fallback к отправке только текста для видео")
            if edit_message_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=edit_message_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return edit_message_id
                except Exception as edit_error:
                    logger.error(f"Не удалось отредактировать сообщение: {edit_error}")
                    # Если не удалось отредактировать, удаляем старое и отправляем новое
                    try:
                        await message.bot.delete_message(chat_id=message.chat.id, message_id=edit_message_id)
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
                    except Exception as delete_error:
                        logger.error(f"Не удалось удалить старое сообщение: {delete_error}")
                        # Если удаление не удалось, все равно отправляем новое
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
            else:
                sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                return sent.message_id
    
    elif media.get("animation"):
        try:
            if edit_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=edit_message_id,
                    media=types.InputMediaAnimation(media=media["animation"], caption=text, parse_mode="HTML"),
                    reply_markup=keyboard
                )
                return edit_message_id
            else:
                sent = await message.answer_animation(
                    animation=media["animation"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return sent.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке анимации: {e}")
            # Fallback к тексту
            logger.info("Fallback к отправке только текста для анимации")
            if edit_message_id:
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=edit_message_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return edit_message_id
                except Exception as edit_error:
                    logger.error(f"Не удалось отредактировать сообщение: {edit_error}")
                    # Если не удалось отредактировать, удаляем старое и отправляем новое
                    try:
                        await message.bot.delete_message(chat_id=message.chat.id, message_id=edit_message_id)
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
                    except Exception as delete_error:
                        logger.error(f"Не удалось удалить старое сообщение: {delete_error}")
                        # Если удаление не удалось, все равно отправляем новое
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
            else:
                sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                return sent.message_id
    
    elif media.get("photo"):
        try:
            logger.info(f"Отправляем фото: {media['photo']}")
            if edit_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=edit_message_id,
                    media=types.InputMediaPhoto(media=media["photo"], caption=text, parse_mode="HTML"),
                    reply_markup=keyboard
                )
                return edit_message_id
            else:
                sent = await message.answer_photo(
                    photo=media["photo"],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return sent.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            # Fallback: скачиваем файл и отправляем как BufferedInputFile
            try:
                import requests
                from aiogram.types import BufferedInputFile
                
                # Устанавливаем короткий таймаут
                response = requests.get(media["photo"], timeout=5)
                if response.status_code == 200:
                    # Определяем расширение файла
                    ext = "jpg"  # По умолчанию
                    if ".png" in media["photo"].lower():
                        ext = "png"
                    elif ".webp" in media["photo"].lower():
                        ext = "webp"
                    elif ".gif" in media["photo"].lower():
                        ext = "gif"
                    
                    photo_file = BufferedInputFile(response.content, filename=f"photo.{ext}")
                    
                    if edit_message_id:
                        await message.bot.edit_message_media(
                            chat_id=message.chat.id,
                            message_id=edit_message_id,
                            media=types.InputMediaPhoto(media=photo_file, caption=text, parse_mode="HTML"),
                            reply_markup=keyboard
                        )
                        return edit_message_id
                    else:
                        sent = await message.answer_photo(
                            photo=photo_file,
                            caption=text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        return sent.message_id
                else:
                    logger.error(f"Не удалось скачать фото: {response.status_code}")
            except Exception as download_error:
                logger.error(f"Ошибка при скачивании фото: {download_error}")
                
                # Дополнительный fallback для Telegram медиа
                if "cdn4.telesco.pe" in media["photo"]:
                    try:
                        # Пробуем с другим User-Agent
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                        response = requests.get(media["photo"], headers=headers, timeout=10)
                        if response.status_code == 200:
                            photo_file = BufferedInputFile(response.content, filename="photo.jpg")
                            
                            if edit_message_id:
                                await message.bot.edit_message_media(
                                    chat_id=message.chat.id,
                                    message_id=edit_message_id,
                                    media=types.InputMediaPhoto(media=photo_file, caption=text, parse_mode="HTML"),
                                    reply_markup=keyboard
                                )
                                return edit_message_id
                            else:
                                sent = await message.answer_photo(
                                    photo=photo_file,
                                    caption=text,
                                    parse_mode="HTML",
                                    reply_markup=keyboard
                                )
                                return sent.message_id
                    except Exception as telegram_fallback_error:
                        logger.error(f"Telegram fallback тоже не сработал: {telegram_fallback_error}")
            
            # Если все fallback не сработали, отправляем только текст
            logger.info("Fallback к отправке только текста")
            if edit_message_id:
                try:
                    # Пытаемся отредактировать существующее сообщение
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=edit_message_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return edit_message_id
                except Exception as edit_error:
                    logger.error(f"Не удалось отредактировать сообщение: {edit_error}")
                    # Если не удалось отредактировать, удаляем старое и отправляем новое
                    try:
                        await message.bot.delete_message(chat_id=message.chat.id, message_id=edit_message_id)
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
                    except Exception as delete_error:
                        logger.error(f"Не удалось удалить старое сообщение: {delete_error}")
                        # Если удаление не удалось, все равно отправляем новое
                        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                        return sent.message_id
            else:
                sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                return sent.message_id
    
    # Если нет медиа или ошибка - отправляем текст
    if edit_message_id:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=edit_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return edit_message_id
    else:
        sent = await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return sent.message_id

async def _load_more_posts_if_needed(navigator: NewsNavigator, user_id: int) -> bool:
    """Загружает больше новостей если нужно. Возвращает True если загружено."""
    if not navigator.needs_more_posts():
        return False
    
    try:
        # Определяем источник и загружаем больше новостей
        current_post = navigator.get_current_post()
        if not current_post:
            return False
        
        source = current_post.get("source", "")
        
        if source == "habr.com":
            # Загружаем больше новостей с Habr
            from parsers.habr_parser import HabrParser
            habr_parser = HabrParser()
            current_count = len(navigator.posts)
            new_posts = habr_parser.get_latest_news(limit=current_count + 10)
            
            if len(new_posts) > current_count:
                # Добавляем только новые новости
                existing_links = {p.get("link") for p in navigator.posts}
                for post in new_posts:
                    if post.get("link") not in existing_links:
                        navigator.posts.append(post)
                return True
                
        else:
            # Загружаем больше новостей с Telegram
            days = 2 if len(navigator.posts) < 10 else 3
            new_posts = await _collect_posts(days=days)
            
            if new_posts:
                # Добавляем только новые новости
                existing_links = {p.get("link") for p in navigator.posts}
                for post in new_posts:
                    if post.get("link") not in existing_links:
                        post['source'] = 'telegram'
                        navigator.posts.append(post)
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке дополнительных новостей: {e}")
        return False

# ===== News Navigation Callbacks =====

@dp.callback_query(lambda c: c.data == "news_next")
async def news_next_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    # Защита от спама - проверяем cooldown
    current_time = time.time()
    if user_id in NAVIGATION_COOLDOWN:
        if current_time - NAVIGATION_COOLDOWN[user_id] < 1.0:  # 1 секунда между нажатиями
            await call.answer("⏳ Подождите немного перед следующим нажатием", show_alert=False)
            return
    
    NAVIGATION_COOLDOWN[user_id] = current_time
    
    if user_id not in NEWS_NAVIGATION:
        await call.message.answer("❌ Сессия навигации не найдена. Начните заново.")
        return
    
    navigator = NEWS_NAVIGATION[user_id]
    
    # Проверяем, нужно ли загрузить больше новостей
    await _load_more_posts_if_needed(navigator, user_id)
    
    if navigator.next_post():
        # Обновляем сообщение
        try:
            message_id = await _send_news_with_media(call.message, navigator, call.message.message_id)
            navigator.message_id = message_id
            NEWS_NAVIGATION[user_id] = navigator
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")
            # Если не удалось отредактировать, отправляем новое и удаляем старое
            try:
                new_message = await _send_news_with_media(call.message, navigator)
                navigator.message_id = new_message
                NEWS_NAVIGATION[user_id] = navigator
                # Удаляем старое сообщение
                await call.message.delete()
            except Exception as delete_error:
                logger.error(f"Не удалось удалить старое сообщение: {delete_error}")
    else:
        await call.answer("Это последняя новость")

@dp.callback_query(lambda c: c.data == "news_prev")
async def news_prev_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    # Защита от спама - проверяем cooldown
    current_time = time.time()
    if user_id in NAVIGATION_COOLDOWN:
        if current_time - NAVIGATION_COOLDOWN[user_id] < 1.0:  # 1 секунда между нажатиями
            await call.answer("⏳ Подождите немного перед следующим нажатием", show_alert=False)
            return
    
    NAVIGATION_COOLDOWN[user_id] = current_time
    
    if user_id not in NEWS_NAVIGATION:
        await call.message.answer("❌ Сессия навигации не найдена. Начните заново.")
        return
    
    navigator = NEWS_NAVIGATION[user_id]
    if navigator.prev_post():
        # Обновляем сообщение
        try:
            message_id = await _send_news_with_media(call.message, navigator, call.message.message_id)
            navigator.message_id = message_id
            NEWS_NAVIGATION[user_id] = navigator
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")
            # Если не удалось отредактировать, отправляем новое
            message_id = await _send_news_with_media(call.message, navigator)
            navigator.message_id = message_id
            NEWS_NAVIGATION[user_id] = navigator
    else:
        await call.answer("Это первая новость")

# Новые обработчики для встроенного просмотра
@dp.callback_query(lambda c: c.data == "view_tldr")
async def view_tldr_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    logger.info(f"DEBUG: view_tldr_callback вызван для пользователя {user_id}")
    
    # Защита от спама - проверяем cooldown
    current_time = time.time()
    if user_id in NAVIGATION_COOLDOWN:
        if current_time - NAVIGATION_COOLDOWN[user_id] < 0.5:  # 0.5 секунды между нажатиями
            await call.answer("⏳ Подождите немного", show_alert=False)
            return
    
    NAVIGATION_COOLDOWN[user_id] = current_time
    
    if user_id not in NEWS_NAVIGATION:
        logger.error(f"DEBUG: Навигация не найдена для пользователя {user_id}")
        return
    
    navigator = NEWS_NAVIGATION[user_id]
    post = navigator.get_current_post()
    if not post:
        logger.error(f"DEBUG: Текущий пост не найден для пользователя {user_id}")
        return
    
    logger.info(f"DEBUG: Текущий пост: {post.get('title', 'Без заголовка')[:50]}...")
    
    # ВСЕГДА загружаем контент заново для текущего поста
    try:
        logger.info(f"DEBUG: Загружаем контент для поста: {post.get('title', 'Без заголовка')[:50]}...")
        logger.info(f"DEBUG: URL поста: {post.get('link', 'НЕТ')}")
        
        parser_obj = _choose_article_parser(post.get("link", ""))
        res = parser_obj.parse_full_article(post.get("link", ""))
        
        if res.get("success"):
            content = res.get("content", "")
            current_title = post.get("title", "")
            
            # Логируем для отладки
            logger.info(f"DEBUG: Загружен контент для поста: {current_title[:50]}...")
            logger.info(f"DEBUG: Длина загруженного контента: {len(content)} символов")
            logger.info(f"DEBUG: Начало контента: {content[:100]}...")
            
            # Всегда используем полученный контент (даже если он не идеально релевантен)
            logger.info(f"DEBUG: Используем полученный контент")
            # Сохраняем полный контент
            navigator.set_post_content("full", content)
            # Создаем краткое содержание
            summary = _summarize_text(content)
            navigator.set_post_content("tldr", summary)
        else:
            logger.error(f"DEBUG: Не удалось получить контент: {res.get('error', 'Неизвестная ошибка')}")
            # Используем заголовок как fallback
            navigator.set_post_content("full", post.get("title", ""))
            navigator.set_post_content("tldr", post.get("title", ""))
    except Exception as e:
        logger.error(f"Ошибка при получении краткого содержания: {e}")
        # Используем заголовок как fallback
        navigator.set_post_content("full", post.get("title", ""))
        navigator.set_post_content("tldr", post.get("title", ""))
    
    # Переключаемся в режим краткого содержания
    navigator.set_view_mode("tldr")
    
    # Обновляем сообщение
    try:
        message_id = await _send_news_with_media(call.message, navigator, call.message.message_id)
        navigator.message_id = message_id
        NEWS_NAVIGATION[user_id] = navigator
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")
        await call.answer("❌ Ошибка при обновлении")

@dp.callback_query(lambda c: c.data == "view_full")
async def view_full_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    logger.info(f"DEBUG: view_full_callback вызван для пользователя {user_id}")
    
    # Защита от спама - проверяем cooldown
    current_time = time.time()
    if user_id in NAVIGATION_COOLDOWN:
        if current_time - NAVIGATION_COOLDOWN[user_id] < 0.5:  # 0.5 секунды между нажатиями
            await call.answer("⏳ Подождите немного", show_alert=False)
            return
    
    NAVIGATION_COOLDOWN[user_id] = current_time
    
    if user_id not in NEWS_NAVIGATION:
        logger.error(f"DEBUG: Навигация не найдена для пользователя {user_id}")
        return
    
    navigator = NEWS_NAVIGATION[user_id]
    post = navigator.get_current_post()
    if not post:
        logger.error(f"DEBUG: Текущий пост не найден для пользователя {user_id}")
        return
    
    logger.info(f"DEBUG: Текущий пост: {post.get('title', 'Без заголовка')[:50]}...")
    
    # ВСЕГДА загружаем контент заново для текущего поста
    try:
        logger.info(f"DEBUG: Загружаем контент для поста: {post.get('title', 'Без заголовка')[:50]}...")
        logger.info(f"DEBUG: URL поста: {post.get('link', 'НЕТ')}")
        
        parser_obj = _choose_article_parser(post.get("link", ""))
        res = parser_obj.parse_full_article(post.get("link", ""))
        
        if res.get("success"):
            content = res.get("content", "")
            current_title = post.get("title", "")
            
            logger.info(f"DEBUG: Загружен контент для поста: {current_title[:50]}...")
            logger.info(f"DEBUG: Длина загруженного контента: {len(content)} символов")
            logger.info(f"DEBUG: Начало контента: {content[:100]}...")
            
            # Всегда используем полученный контент (даже если он не идеально релевантен)
            logger.info(f"DEBUG: Используем полученный контент")
            # Сохраняем полный контент
            navigator.set_post_content("full", content)
            # Создаем краткое содержание для кнопки "Кратко"
            summary = _summarize_text(content)
            navigator.set_post_content("tldr", summary)
        else:
            logger.error(f"DEBUG: Не удалось получить контент: {res.get('error', 'Неизвестная ошибка')}")
            # Используем заголовок как fallback
            navigator.set_post_content("full", post.get("title", ""))
            navigator.set_post_content("tldr", post.get("title", ""))
    except Exception as e:
        logger.error(f"Ошибка при получении полной статьи: {e}")
        # Используем заголовок как fallback
        navigator.set_post_content("full", post.get("title", ""))
        navigator.set_post_content("tldr", post.get("title", ""))
    
    # Переключаемся в режим полной статьи
    navigator.set_view_mode("full")
    
    # Обновляем сообщение
    try:
        message_id = await _send_news_with_media(call.message, navigator, call.message.message_id)
        navigator.message_id = message_id
        NEWS_NAVIGATION[user_id] = navigator
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")
        await call.answer("❌ Ошибка при обновлении")

@dp.callback_query(lambda c: c.data == "view_normal")
async def view_normal_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    # Защита от спама - проверяем cooldown
    current_time = time.time()
    if user_id in NAVIGATION_COOLDOWN:
        if current_time - NAVIGATION_COOLDOWN[user_id] < 0.5:  # 0.5 секунды между нажатиями
            await call.answer("⏳ Подождите немного", show_alert=False)
            return
    
    NAVIGATION_COOLDOWN[user_id] = current_time
    
    if user_id not in NEWS_NAVIGATION:
        return
    
    navigator = NEWS_NAVIGATION[user_id]
    navigator.set_view_mode("normal")
    
    # Обновляем сообщение в обычном режиме
    try:
        message_id = await _send_news_with_media(call.message, navigator, call.message.message_id)
        navigator.message_id = message_id
        NEWS_NAVIGATION[user_id] = navigator
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")

@dp.callback_query(lambda c: c.data == "news_exit")
async def news_exit_callback(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    
    # Удаляем сессию навигации
    if user_id in NEWS_NAVIGATION:
        del NEWS_NAVIGATION[user_id]
    
    # Создаем inline-клавиатуру для главного меню
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    
    main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 Последние новости", callback_data="latest_news")],
        [InlineKeyboardButton(text="📊 Топ за сегодня", callback_data="top_news")],
        [InlineKeyboardButton(text="🔍 Поиск по запросу", callback_data="search_news")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="favorites")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])
    
    # Пытаемся отредактировать сообщение, если не получается - отправляем новое
    try:
        await call.message.edit_text("📰 Выберите, какие новости вы хотите увидеть:", reply_markup=main_menu_keyboard)
    except Exception as e:
        logger.error(f"Не удалось отредактировать сообщение: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        try:
            await call.message.answer("📰 Выберите, какие новости вы хотите увидеть:", reply_markup=main_menu_keyboard)
            # Удаляем старое сообщение
            await call.message.delete()
        except Exception as delete_error:
            logger.error(f"Не удалось удалить старое сообщение: {delete_error}")

# ===== Admin broadcast =====

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast_menu(call: CallbackQuery) -> None:
    await call.answer()
    if not is_admin(call.from_user.id):
        return
    from .admin import get_broadcast_keyboard
    await call.message.edit_text("📢 <b>Рассылка</b>\nВыберите режим:", parse_mode="HTML", reply_markup=get_broadcast_keyboard())

@dp.callback_query(lambda c: c.data == "admin_broadcast_all")
async def admin_broadcast_all(call: CallbackQuery, state=None) -> None:
    await call.answer()
    if not is_admin(call.from_user.id):
        return
    BROADCAST_ALL_WAITING.add(call.from_user.id)
    await call.message.edit_text("✍️ Введите текст рассылки для всех пользователей:")

@dp.callback_query(lambda c: c.data == "admin_broadcast_user")
async def admin_broadcast_user(call: CallbackQuery) -> None:
    await call.answer()
    if not is_admin(call.from_user.id):
        return
    BROADCAST_USER_WAITING.add(call.from_user.id)
    await call.message.edit_text("✍️ Введите: ID_пользователя пробел текст сообщения")

@dp.callback_query(lambda c: c.data == "main_menu")
async def go_main_menu(call: CallbackQuery) -> None:
    await call.answer()
    
    # Создаем inline-клавиатуру для главного меню
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    
    main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 Последние новости", callback_data="latest_news")],
        [InlineKeyboardButton(text="📊 Топ за сегодня", callback_data="top_news")],
        [InlineKeyboardButton(text="🔍 Поиск по запросу", callback_data="search_news")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="favorites")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])
    
    # Пытаемся отредактировать сообщение, если не получается - отправляем новое
    try:
        await call.message.edit_text("📰 Выберите, какие новости вы хотите увидеть:", reply_markup=main_menu_keyboard)
    except Exception as e:
        logger.error(f"Не удалось отредактировать сообщение: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        try:
            await call.message.answer("📰 Выберите, какие новости вы хотите увидеть:", reply_markup=main_menu_keyboard)
            # Удаляем старое сообщение
            await call.message.delete()
        except Exception as delete_error:
            logger.error(f"Не удалось удалить старое сообщение: {delete_error}")

# ===== Main menu callbacks =====

@dp.callback_query(lambda c: c.data == "latest_news")
async def latest_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    await latest_news(call.message)

@dp.callback_query(lambda c: c.data == "top_news")
async def top_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    await top_command(call.message)

@dp.callback_query(lambda c: c.data == "search_news")
async def search_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    await ask_search_query(call.message)

@dp.callback_query(lambda c: c.data == "favorites")
async def favorites_callback(call: CallbackQuery) -> None:
    await call.answer()
    await show_favorites(call.message)

@dp.callback_query(lambda c: c.data == "stats")
async def stats_callback(call: CallbackQuery) -> None:
    await call.answer()
    await show_stats(call.message)

@dp.callback_query(lambda c: c.data == "settings")
async def settings_callback(call: CallbackQuery) -> None:
    await call.answer()
    await show_settings(call.message)

# ===== Habr "Еще новости" callback =====

@dp.callback_query(lambda c: c.data.startswith("more_habr_news"))
async def more_habr_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    try:
        parts = call.data.split(":")
        offset = int(parts[1]) if len(parts) > 1 else 10
        
        await call.message.edit_text("🔄 Загружаю дополнительные IT новости с Habr...")
        
        from parsers.habr_parser import HabrParser
        habr_parser = HabrParser()
        posts = habr_parser.get_more_news(offset=offset, limit=15)
        
        if not posts:
            await call.message.edit_text("❌ Больше новостей не найдено")
            return
        
        # Создаем новый навигатор для дополнительных новостей
        navigator = NewsNavigator(posts, 0) # Start from index 0
        NEWS_NAVIGATION[call.from_user.id] = navigator
        
        # Отправляем первую новость из новой порции
        text = navigator.get_navigation_text()
        keyboard = navigator.get_navigation_keyboard()
        
        sent_message = await call.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        
        # Сохраняем ID сообщения для редактирования
        navigator.message_id = sent_message.message_id
        NEWS_NAVIGATION[call.from_user.id] = navigator
        
        # Удаляем старое сообщение
        try:
            await call.message.delete()
        except Exception as e:
            logger.error(f"Ошибка при удалении старого сообщения: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке дополнительных новостей с Habr: {e}")
        await call.message.edit_text("❌ Произошла ошибка при загрузке новостей")

# Fallback

@dp.callback_query()
async def unknown_callback(call: CallbackQuery) -> None:
    await call.answer("❌ Неизвестная команда")
    logger.warning(f"Неизвестный callback: {call.data}")

@dp.message()
async def handle_all_messages(message: Message) -> None:
    await message.answer("Используйте /start или меню ниже", reply_markup=get_main_keyboard())

async def main() -> None:
    init_db()
    logger.info("База данных инициализирована")
    scheduler = NewsScheduler()
    scheduler.bot = bot
    await scheduler.setup_all_schedules()
    logger.info("Планировщик новостей запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())