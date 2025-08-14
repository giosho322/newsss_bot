#!/usr/bin/env python3
"""
Telegram News Bot (возвращены: последние новости, поиск, избранное, статистика, админ-панель)
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, BufferedInputFile
import aiohttp

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

MENU_TEXTS = {
    "📰 Последние новости",
    "📊 Топ за сегодня",
    "🔍 Поиск по запросу",
    "⭐ Избранное",
    "📈 Статистика",
    "⚙️ Настройки",
}

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
    for channel_url in TELEGRAM_CHANNELS:
        try:
            posts = parser.parse_channel(channel_url, limit=60)
            for p in posts:
                p_date = _to_date(p.get("date", ""))
                if p_date >= threshold:
                    all_posts.append(p)
        except Exception as e:
            logger.error(f"Ошибка при парсинге {channel_url}: {e}")
            continue
    # Сортируем по популярности (views), затем по дате
    all_posts.sort(key=lambda x: (x.get("views", 0), x.get("date", "")), reverse=True)
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
    await message.answer("�� Загружаю последние IT новости с Habr...")
    try:
        from parsers.habr_parser import HabrParser
        habr_parser = HabrParser()
        posts = habr_parser.get_latest_news(limit=10)
        
        if not posts:
            await message.answer("❌ Не удалось загрузить новости с Habr")
            return
            
        limit = get_user_news_count(message.from_user.id)
        posts = posts[:limit]
        
        for p in posts:
            title = p.get("title", "Без заголовка")
            link = p.get("link", "")
            summary = p.get("summary", "")
            date = p.get("date", "")
            
            caption = f"<b>{title}</b>\n\n{summary}\n\n📅 {date}\n🔗 Источник: Habr"
            
            if link:
                try:
                    add_view_history(message.from_user.id, link, 0)
                except Exception:
                    pass
                    
            await message.answer(caption, parse_mode="HTML", reply_markup=get_post_keyboard(link))
        
        # Кнопка "Еще новости"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Еще новости", callback_data="more_habr_news:10")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("Показаны последние IT новости с Habr", reply_markup=kb)
        
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
        found = habr_parser.search_by_query(query, limit=10)
        
        if not found:
            await message.answer("Ничего не найдено на Habr по вашему запросу")
            return
            
        for p in found[:10]:
            title = p.get("title", "Без заголовка")
            link = p.get("link", "")
            summary = p.get("summary", "")
            
            caption = f"<b>{title}</b>\n\n{summary}\n\n🔍 Найдено по запросу: {query}"
            
            if link:
                try:
                    add_view_history(message.from_user.id, link, 0)
                except Exception:
                    pass
                    
            await message.answer(caption, parse_mode="HTML", reply_markup=get_post_keyboard(link))
            
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
    await message.answer("🔍 Загружаю топ новостей...")
    posts = await _collect_posts(days=1)
    if not posts:
        await message.answer("❌ Не удалось загрузить новости. Попробуйте позже.")
        return
    user_limit = get_user_news_count(message.from_user.id)
    posts_to_show = posts[: max(5, user_limit)]
    for p in posts_to_show:
        title = p.get("title", "Без заголовка")
        link = p.get("link", "")
        channel = p.get("channel", "?")
        views = p.get("views", 0)
        image = p.get("image_url", "")
        video = p.get("video_url", "")
        anim = p.get("animation_url", "")
        caption = f"<b>{title}</b>\n📺 {channel}   👁️ {views}"
        if link:
            try:
                add_view_history(message.from_user.id, link, 0)
            except Exception:
                pass
        # Порядок: видео → гиф → фото → текст
        if await _try_send_video(message, video, caption, reply_markup=get_post_keyboard(link)):
            continue
        if await _try_send_animation(message, anim, caption, reply_markup=get_post_keyboard(link)):
            continue
        if await _try_send_photo(message, image, caption, reply_markup=get_post_keyboard(link)):
            continue
        await message.answer(caption, parse_mode="HTML", reply_markup=get_post_keyboard(link))
    # Кнопка еще
    kb = get_top_news_buttons(more_callback_data="more_top_news:1")
    await message.answer("Показаны топ новости за 1 день", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("top_news"))
async def top_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    await top_command(call.message)

@dp.callback_query(lambda c: c.data.startswith("more_top_news"))
async def more_top_news_callback(call: CallbackQuery) -> None:
    await call.answer()
    try:
        parts = call.data.split(":")
        prev_days = int(parts[1]) if len(parts) > 1 else 1
        days = min(prev_days + 1, 7)
        await call.message.edit_text("🔍 Загружаю дополнительные новости...")
        posts = await _collect_posts(days=days)
        if not posts:
            await call.message.edit_text("❌ Не удалось загрузить дополнительные новости.")
            return
        user_limit = get_user_news_count(call.from_user.id)
        posts_to_show = posts[: max(5, user_limit)]
        for p in posts_to_show:
            title = p.get("title", "Без заголовка")
            link = p.get("link", "")
            channel = p.get("channel", "?")
            views = p.get("views", 0)
            image = p.get("image_url", "")
            video = p.get("video_url", "")
            anim = p.get("animation_url", "")
            caption = f"<b>{title}</b>\n📺 {channel}   👁️ {views}"
            if link:
                try:
                    add_view_history(call.from_user.id, link, 0)
                except Exception:
                    pass
            if await _try_send_video(call.message, video, caption, reply_markup=get_post_keyboard(link)):
                continue
            if await _try_send_animation(call.message, anim, caption, reply_markup=get_post_keyboard(link)):
                continue
            if await _try_send_photo(call.message, image, caption, reply_markup=get_post_keyboard(link)):
                continue
            await call.message.answer(caption, parse_mode="HTML", reply_markup=get_post_keyboard(link))
        # Итоговое сообщение
        await call.message.answer(f"Показаны новости за {days} д.", reply_markup=get_top_news_buttons(more_callback_data=f"more_top_news:{days}"))
    except Exception as e:
        logger.error(f"Ошибка при загрузке дополнительных новостей: {e}")
        await call.message.edit_text("❌ Произошла ошибка при загрузке новостей")

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
    save_news(call.from_user.id, title=title, url=link)
    await call.message.edit_reply_markup(reply_markup=get_post_keyboard(link))

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
    return BaseParser()

def _summarize_text(text: str, max_chars: int = 900) -> str:
    if not text:
        return ""
    # Простое суммирование: первые 5 предложений или ограничение по символам
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    summary = ". ".join(sentences[:5])
    if not summary:
        summary = text[:max_chars]
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "..."
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
    await call.message.answer("🏠 Главное меню", reply_markup=get_main_menu())

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
        posts = habr_parser.get_more_news(offset=offset, limit=5)
        
        if not posts:
            await call.message.edit_text("❌ Больше новостей не найдено")
            return
            
        for p in posts:
            title = p.get("title", "Без заголовка")
            link = p.get("link", "")
            summary = p.get("summary", "")
            date = p.get("date", "")
            
            caption = f"<b>{title}</b>\n\n{summary}\n\n📅 {date}\n🔗 Источник: Habr"
            
            if link:
                try:
                    add_view_history(call.from_user.id, link, 0)
                except Exception:
                    pass
                    
            await call.message.answer(caption, parse_mode="HTML", reply_markup=get_post_keyboard(link))
        
        # Кнопка для следующей порции
        next_offset = offset + 5
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Еще новости", callback_data=f"more_habr_news:{next_offset}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await call.message.answer(f"Показаны IT новости с Habr (с {offset+1} по {offset+len(posts)})", reply_markup=kb)
        
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