import asyncio
import logging
import io
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from .config import BOT_TOKEN, TELEGRAM_CHANNELS
from .keyboards import (
    get_main_menu,
    get_themes_menu,
    get_news_buttons,
    get_full_article_buttons,
    get_top_news_buttons,
    get_top_news_initial_buttons,
    get_manage_channels_buttons,
    get_cancel_button,
    get_settings_buttons,
    get_post_action_buttons,
    get_digest_schedule_buttons,
    get_time_selection_buttons,
    get_days_selection_buttons,
    get_theme_selection_buttons,
    get_notification_settings_buttons,
    get_statistics_buttons,
    get_rating_buttons,
    get_comment_buttons,
    get_recommendations_buttons,
    get_export_format_buttons,
    get_search_advanced_buttons,
    get_archive_buttons,
)
from .utils import (
    format_news_message, 
    format_favorites_list, 
    clean_html, 
    summarize_text, 
    apply_filters,
    analyze_user_activity,
    generate_recommendations,
    export_to_markdown,
    export_to_csv,
    export_to_json,
    generate_activity_summary,
    format_notification_message,
    extract_tags_from_text,
    calculate_reading_time,
    format_time_spent,
)
from .scheduler import NewsScheduler
from parsers.habr_parser import HabrParser
from parsers.telegram_parser import TelegramParser
from database.db import (
    init_db,
    add_user,
    save_news,
    get_favorites,
    get_user_channels,
    set_user_channels,
    get_user_news_count,
    set_user_news_count,
    get_user_filters,
    set_user_filters,
    add_view_history,
    get_user_stats,
    add_search_query,
    add_comment,
    get_post_comments,
    add_post_rating,
    get_post_rating,
    add_recommendation,
    get_recommendations,
    set_digest_schedule,
    get_digest_schedule,
    add_notification,
    get_unread_notifications,
    mark_notification_read,
    archive_post,
    add_tag,
    get_popular_tags,
    add_export_record,
    update_user_activity,
    get_active_users,
    get_view_history,
    delete_notification,
    get_user_theme,
    set_user_theme,
    get_user_notification_settings,
    set_user_notification_settings,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Определяем состояния для FSM
class SearchStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_channel_input = State()  # Для ввода нового канала
    waiting_for_filter_input = State()   # Для ввода ключевых слов фильтра
    waiting_for_comment_input = State()  # Для ввода комментария
    waiting_for_time_input = State()     # Для ввода времени дайджеста
    waiting_for_days_input = State()     # Для выбора дней недели
    waiting_for_theme_input = State()    # Для выбора темы оформления
    waiting_for_advanced_search = State() # Для расширенного поиска

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
parser = HabrParser()
tg_parser = TelegramParser()
scheduler = NewsScheduler(bot)  # Планировщик для автоматических дайджестов

# Хранилище для новостей
news_cache = {}
top_news_cache = {}  # Для кэширования топ новостей

@dp.message(Command("start"))
async def cmd_start(message: Message):
    add_user(message.from_user.id)
    await message.answer(
        "👋 Привет! Я бот новостей из мира IT и программирования!\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_menu(),
    )

@dp.message(Command("test_parser"))
async def test_parser(message: Message):
    """Тестирование парсера для конкретного канала"""
    try:
        # Тестируем на примере
        test_channel = "https://t.me/tproger"
        await message.answer(f"🔍 Тестирую парсер на канале: {test_channel}")
        
        posts = tg_parser.parse_channel(test_channel, 3)
        if posts:
            result = f"✅ Парсер работает! Получено {len(posts)} постов:\n\n"
            for i, post in enumerate(posts[:3], 1):
                title = post.get('title', 'Без заголовка')[:100]
                text = post.get('text', '')[:200]
                result += f"{i}. {title}\n"
                if text:
                    result += f"   {text}\n"
                result += f"   Ссылка: {post.get('link', 'Нет')}\n\n"
        else:
            result = "❌ Парсер не смог получить посты"
        
        await message.answer(result)
    except Exception as e:
        logging.error(f"Ошибка при тестировании парсера: {e}")
        await message.answer(f"❌ Ошибка тестирования: {str(e)}")

@dp.message(lambda message: message.text == "📰 Последние новости")
async def get_latest_news(message: Message):
    await message.answer("🔍 Загружаю последние новости...")

    try:
        # Учитываем фильтры и размер пачки
        include_keys, exclude_keys = get_user_filters(message.from_user.id)
        per_batch = get_user_news_count(message.from_user.id)

        news_list = parser.get_latest_news(limit=per_batch * 2)
        news_list = apply_filters(news_list, include_keys, exclude_keys)
        news_list = news_list[:per_batch]

        if not news_list:
            await message.answer("❌ Не удалось загрузить новости. Попробуйте позже.")
            return

        for i, news in enumerate(news_list):
            news_id = f"habr_{i}"
            news_cache[news_id] = news

            msg = format_news_message(news)
            await message.answer(
                msg,
                reply_markup=get_news_buttons(news["link"], news_id),
                parse_mode="HTML",
            )
            
            # Добавляем задержку между сообщениями (кроме последнего)
            if i < len(news_list) - 1:
                await asyncio.sleep(1.5)  # 1.5 секунды задержки

    except Exception as e:
        logging.error(f"Ошибка при получении новостей: {e}")
        await message.answer("❌ Произошла ошибка при загрузке новостей.")

@dp.message(lambda message: message.text == "🔍 Поиск по темам")
async def search_themes(message: Message):
    await message.answer("Выберите тему для поиска:", reply_markup=get_themes_menu())

@dp.message(lambda message: message.text == "🎯 Поиск по запросу")
async def start_search_query(message: Message, state: FSMContext):
    await message.answer("Введите поисковый запрос (например: 'Python machine learning'):")
    await state.set_state(SearchStates.waiting_for_query)

@dp.message(SearchStates.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    query = message.text.strip()

    if not query:
        await message.answer("Пожалуйста, введите непустой поисковый запрос.")
        return

    await message.answer(f"🔍 Ищем новости по запросу: {query}")

    try:
        include_keys, exclude_keys = get_user_filters(message.from_user.id)
        per_batch = get_user_news_count(message.from_user.id)
        news_list = parser.search_by_query(query, limit=per_batch * 2)
        news_list = apply_filters(news_list, include_keys, exclude_keys)[:per_batch]

        if not news_list:
            await message.answer(
                f"❌ Не найдено новостей по запросу: {query}\n"
                "Попробуйте изменить запрос или поискать что-то другое.",
                reply_markup=get_main_menu(),
            )
            await state.clear()
            return

        for i, news in enumerate(news_list):
            news_id = f"search_{hash(query + str(i)) % 1000000}"
            news_cache[news_id] = news

            msg = format_news_message(news)
            await message.answer(
                msg,
                reply_markup=get_news_buttons(news["link"], news_id),
                parse_mode="HTML",
            )
            
            # Добавляем задержку между сообщениями (кроме последнего)
            if i < len(news_list) - 1:
                await asyncio.sleep(1.5)  # 1.5 секунды задержки

        await message.answer("Выберите действие из меню:", reply_markup=get_main_menu())

    except Exception as e:
        logging.error(f"Ошибка при поиске новостей по запросу '{query}': {e}")
        await message.answer(
            f"❌ Произошла ошибка при поиске новостей по запросу: {query}",
            reply_markup=get_main_menu(),
        )

    await state.clear()

@dp.callback_query(lambda call: call.data == "add_channel")
async def add_channel_callback(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "Введите ссылку на Telegram канал в формате:\n"
        "<code>https://t.me/channel_name</code>\n"
        "или <code>@channel_name</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_button()
    )
    await state.set_state(SearchStates.waiting_for_channel_input)
    await call.answer()

@dp.message(SearchStates.waiting_for_channel_input)
async def process_channel_input(message: Message, state: FSMContext):
    channel_input = message.text.strip()
    
    # Валидация ввода
    if not channel_input:
        await message.answer("Пожалуйста, введите корректную ссылку на канал.")
        return
    
    # Нормализация ссылки
    if channel_input.startswith('@'):
        channel_url = f"https://t.me/{channel_input[1:]}"
    elif channel_input.startswith('https://t.me/'):
        channel_url = channel_input
    else:
        channel_url = f"https://t.me/{channel_input}"
    
    # Получаем текущие каналы пользователя
    current_channels = get_user_channels(message.from_user.id)
    
    # Добавляем новый канал
    if channel_url not in current_channels:
        current_channels.append(channel_url)
        set_user_channels(message.from_user.id, current_channels)
        await message.answer(f"✅ Канал {channel_url} успешно добавлен!")
    else:
        await message.answer("Этот канал уже есть в вашем списке.")
    
    # Показываем обновленный список каналов
    user_channels = get_user_channels(message.from_user.id)
    channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
    if len(user_channels) > 10:
        channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
    
    await message.answer(
        f"⚙️ <b>Управление каналами</b>\n\n<b>Ваши Telegram каналы:</b>\n{channels_list}",
        reply_markup=get_manage_channels_buttons(user_channels),
        parse_mode="HTML"
    )
    
    await state.clear()

@dp.message(lambda message: message.text == "📊 Топ за сегодня")
async def get_top_news_today(message: Message):
    # Показываем меню с выбором действия
    await message.answer(
        "📊 <b>Топ новостей за сегодня</b>\n\n"
        "Выберите действие:",
        reply_markup=get_top_news_initial_buttons(),
        parse_mode="HTML"
    )

# Обработчики новых callback-кнопок
# --- НАЧАЛО ФУНКЦИИ view_top_today_callback ---
@dp.callback_query(lambda call: call.data == "view_top_today")
async def view_top_today_callback(call: CallbackQuery):
    await call.answer("📊 Загружаю топ новостей за сегодня...")
    
    try:
        # Получаем каналы пользователя
        channels = get_user_channels(call.from_user.id)
        
        if not channels:
            try:
                await call.message.edit_text(
                    "❌ У вас не добавлено ни одного канала для мониторинга.\n"
                    "Нажмите '⚙️ Изменить каналы', чтобы добавить каналы.",
                    reply_markup=get_top_news_initial_buttons()
                )
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    await call.answer("Нет каналов для мониторинга")
                else:
                    raise e
            return
        
        # Показываем пользователю, что идет загрузка
        try:
            await call.message.edit_text("⏳ Идет анализ каналов...")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                raise e
        
        # Получаем посты из всех каналов
        all_posts = []
        for channel_url in channels[:3]:  # Ограничиваем до 3 каналов для теста
            try:
                posts = tg_parser.parse_channel(channel_url, 2)
                all_posts.extend(posts)
            except Exception as e:
                logging.error(f"Ошибка при обработке канала {channel_url}: {e}")
                continue
        
        # Удаляем сообщение о прогрессе и показываем результат
        if not all_posts:
            logging.warning("Не удалось получить посты ни с одного канала")
            try:
                await call.message.edit_text(
                    "❌ Не удалось загрузить топ новостей. Попробуйте позже.\n"
                    "Возможные причины:\n"
                    "• Каналы недоступны или приватные\n"
                    "• Проблемы с сетью\n"
                    "• Каналы не содержат постов",
                    reply_markup=get_top_news_initial_buttons()
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
            return
        
        # Сортируем посты по дате (новые первыми)
        all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Берем первые 4 поста
        posts_to_show = all_posts[:4]
        
        # Сохраняем в кэш для кнопки "Еще новости"
        top_news_cache[call.from_user.id] = {
            'all_posts': all_posts,
            'shown_posts': posts_to_show,
            'channels': channels,
            'per_batch': 4,  # Количество постов за раз
        }
        
        # Обновляем сообщение
        try:
            await call.message.edit_text("✅ Вот топ новостей за сегодня:")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                raise e
        
        # Отправляем посты с задержкой для избежания flood control
        for i, post in enumerate(posts_to_show):
            try:
                post_id = f"top_{call.from_user.id}_{i}"
                news_cache[post_id] = post
                
                # Формируем сообщение
                title = clean_html(post.get('title', 'Без заголовка'))
                text = clean_html(post.get('text', ''))
                
                # Ограничиваем длину текста
                if len(text) > 300:
                    text = text[:300] + "..."
                
                caption = f"📢 <b>{title}</b>\n\n"
                if text:
                    caption += f"💬 {text}\n\n"
                caption += f"📍 Канал: @{post.get('channel', 'Неизвестный канал')}\n"
                caption += f"🔗 <a href='{post.get('link', '')}'>Читать далее</a>"
                
                # Если есть изображение, отправляем как фото
                if post.get('image_url'):
                    try:
                        await call.message.answer_photo(
                            photo=post['image_url'],
                            caption=caption,
                            parse_mode="HTML"
                        )
                    except Exception as photo_error:
                        logging.error(f"Ошибка при отправке фото: {photo_error}")
                        # Если не удалось отправить фото, отправляем как обычное сообщение
                        await call.message.answer(caption, parse_mode="HTML")
                else:
                    # Отправляем как обычное сообщение
                    await call.message.answer(caption, parse_mode="HTML")
                
                # Добавляем задержку между сообщениями (кроме последнего)
                if i < len(posts_to_show) - 1:
                    await asyncio.sleep(1.5) # 1.5 секунды задержки
            except Exception as e:
                logging.error(f"Ошибка при отправке поста: {e}")
                continue
        
        # --- НОВАЯ ЛОГИКА ДЛЯ КНОПКИ "ЕЩЕ НОВОСТИ" ---
        # Проверяем, остались ли ещё посты
        remaining_posts = len(all_posts) - len(posts_to_show)
        
        if remaining_posts > 0:
            # Если есть еще посты, отправляем сообщение с кнопкой "Еще новости"
            await call.message.answer(
                f"🔄 Показано {len(posts_to_show)} из {len(all_posts)}. Осталось ещё {remaining_posts}.",
                reply_markup=get_top_news_buttons()
            )
        else:
            # Если посты закончились, отправляем финальное сообщение
            await call.message.answer("✅ Все доступные посты показаны!", reply_markup=get_top_news_initial_buttons())
        # --- КОНЕЦ НОВОЙ ЛОГИКИ ---
        
    except Exception as e:
        logging.error(f"Ошибка при получении топ новостей: {e}")
        try:
            await call.message.edit_text(
                f"❌ Произошла ошибка при загрузке топ новостей: {str(e)}",
                reply_markup=get_top_news_initial_buttons()
            )
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error).lower():
                logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        await call.answer("Ошибка при загрузке топ новостей")
# --- КОНЕЦ ФУНКЦИИ view_top_today_callback ---

@dp.callback_query(lambda call: call.data == "more_top_news")
async def more_top_news_callback(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer("Загружаю ещё новости...")

    try:
        cache = top_news_cache.get(user_id)
        if not cache:
            try:
                await call.message.edit_text(
                    "❌ Сессия с топ новостями не найдена. Нажмите '👁️ Смотреть топ за сегодня' заново.",
                    reply_markup=get_top_news_initial_buttons()
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
            return

        all_posts = cache.get('all_posts', [])
        shown_posts = cache.get('shown_posts', [])

        start_index = len(shown_posts)
        batch_size = cache.get('per_batch', 4)
        next_posts = all_posts[start_index:start_index + batch_size]

        if not next_posts:
            try:
                await call.message.edit_text(
                    "✅ Новых постов больше нет на сегодня.",
                    reply_markup=get_top_news_initial_buttons()
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
            return

        for i, post in enumerate(next_posts, start=start_index):
            try:
                post_id = f"top_{user_id}_{i}"
                news_cache[post_id] = post

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
                        await call.message.answer_photo(
                            photo=post['image_url'],
                            caption=caption,
                            parse_mode="HTML"
                        )
                    except Exception as photo_error:
                        logging.error(f"Ошибка при отправке фото: {photo_error}")
                        await call.message.answer(caption, parse_mode="HTML")
                else:
                    await call.message.answer(caption, parse_mode="HTML")

                # Добавляем задержку между сообщениями (кроме последнего)
                if i < len(next_posts) - 1:
                    await asyncio.sleep(1.5)  # 1.5 секунды задержки

            except Exception as e:
                logging.error(f"Ошибка при отправке поста: {e}")
                continue

        # Обновляем показанные посты в кэше
        cache['shown_posts'] = shown_posts + next_posts
        top_news_cache[user_id] = cache

        # Удаляем старое сообщение с кнопкой "Еще новости"
        try:
            await call.message.delete()
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения: {e}")

        # Проверяем, остались ли ещё посты для показа
        remaining_posts = len(all_posts) - len(cache['shown_posts'])
        
        if remaining_posts > 0:
            # Если посты ещё есть, отправляем новое сообщение с кнопкой "Ещё новости"
            await call.message.answer(
                f"🔄 Показано {len(cache['shown_posts'])} из {len(all_posts)} постов. Осталось ещё {remaining_posts}.",
                reply_markup=get_top_news_buttons()
            )
        else:
            # Если посты закончились, отправляем финальное сообщение
            await call.message.answer(
                "✅ Все доступные посты показаны!",
                reply_markup=get_top_news_initial_buttons()
            )

    except Exception as e:
        logging.error(f"Ошибка при загрузке дополнительных новостей: {e}")
        try:
            await call.message.edit_text(
                "❌ Произошла ошибка при загрузке дополнительных новостей.",
                reply_markup=get_top_news_initial_buttons()
            )
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error).lower():
                logging.error(f"Ошибка при редактировании сообщения: {edit_error}")
        await call.answer("Ошибка при загрузке")

@dp.callback_query(lambda call: call.data == "manage_channels")
async def manage_channels_callback(call: CallbackQuery):
    user_channels = get_user_channels(call.from_user.id)
    
    if not user_channels:
        message_text = "У вас пока нет добавленных каналов.\n\nНажмите '➕ Добавить канал', чтобы добавить первый канал."
    else:
        channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
        if len(user_channels) > 10:
            channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
        message_text = f"<b>Ваши Telegram каналы:</b>\n{channels_list}"
    
    # Добавляем обработку ошибки "message is not modified"
    try:
        await call.message.edit_text(
            f"⚙️ <b>Управление каналами</b>\n\n{message_text}",
            reply_markup=get_manage_channels_buttons(user_channels),
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" in str(e).lower():
            # Если сообщение не изменилось, просто отвечаем пользователю
            await call.answer("Список каналов не изменился")
        else:
            # Если другая ошибка, пробрасываем её
            raise e
    
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("delete_channel_"))
async def delete_channel_callback(call: CallbackQuery):
    try:
        channel_index = int(call.data.split("_")[-1])
        current_channels = get_user_channels(call.from_user.id)
        
        if 0 <= channel_index < len(current_channels):
            removed_channel = current_channels.pop(channel_index)
            set_user_channels(call.from_user.id, current_channels)
            
            # Показываем обновленный список
            user_channels = get_user_channels(call.from_user.id)
            if not user_channels:
                message_text = "У вас пока нет добавленных каналов.\n\nНажмите '➕ Добавить канал', чтобы добавить первый канал."
            else:
                channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
                if len(user_channels) > 10:
                    channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
                message_text = f"<b>Ваши Telegram каналы:</b>\n{channels_list}"
            
            try:
                await call.message.edit_text(
                    f"✅ Канал {removed_channel} успешно удален!\n\n"
                    f"⚙️ <b>Управление каналами</b>\n\n{message_text}",
                    reply_markup=get_manage_channels_buttons(user_channels),
                    parse_mode="HTML"
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
        else:
            await call.answer("❌ Неверный индекс канала.")
    except ValueError:
        await call.answer("❌ Ошибка при удалении канала.")
    
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("channels_page_"))
async def channels_page_callback(call: CallbackQuery):
    try:
        page = int(call.data.split("_")[-1])
        user_channels = get_user_channels(call.from_user.id)
        
        channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
        if len(user_channels) > 10:
            channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
        
        try:
            await call.message.edit_text(
                f"⚙️ <b>Управление каналами</b>\n\n<b>Ваши Telegram каналы:</b>\n{channels_list}",
                reply_markup=get_manage_channels_buttons(user_channels, page),
                parse_mode="HTML"
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                raise e
    except ValueError:
        await call.answer("❌ Ошибка навигации.")
    
    await call.answer()

@dp.callback_query(lambda call: call.data == "cancel_channel_operation")
async def cancel_channel_operation_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    
    user_channels = get_user_channels(call.from_user.id)
    if not user_channels:
        message_text = "У вас пока нет добавленных каналов.\n\nНажмите '➕ Добавить канал', чтобы добавить первый канал."
    else:
        channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
        if len(user_channels) > 10:
            channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
        message_text = f"<b>Ваши Telegram каналы:</b>\n{channels_list}"
    
    try:
        await call.message.edit_text(
            f"⚙️ <b>Управление каналами</b>\n\n{message_text}",
            reply_markup=get_manage_channels_buttons(user_channels),
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise e
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_top_menu")
async def back_to_top_menu_callback(call: CallbackQuery):
    try:
        await call.message.edit_text(
            "📊 <b>Топ новостей за сегодня</b>\n\n"
            "Выберите действие:",
            reply_markup=get_top_news_initial_buttons(),
            parse_mode="HTML"
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise e
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("theme_"))
async def theme_callback(call: CallbackQuery):
    theme = call.data.split("_")[1]
    theme_names = {
        "python": "Python",
        "js": "JavaScript",
        "ai": "AI/ML",
        "web": "Веб-разработка",
    }

    theme_name = theme_names.get(theme, theme)
    try:
        await call.message.edit_text(f"🔍 Ищем новости по теме: {theme_name}")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise e

    try:
        include_keys, exclude_keys = get_user_filters(call.from_user.id)
        per_batch = get_user_news_count(call.from_user.id)
        news_list = parser.search_by_theme(theme, limit=per_batch * 2)
        news_list = apply_filters(news_list, include_keys, exclude_keys)[:per_batch]

        if not news_list:
            try:
                await call.message.edit_text(
                    f"❌ Не найдено новостей по теме: {theme_name}",
                    reply_markup=get_main_menu(),
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
            return

        # Удаляем сообщение "Ищем новости по теме"
        await call.message.delete()

        # Отправляем новые сообщения с новостями
        for i, news in enumerate(news_list):
            news_id = f"{theme}_{i}"
            news_cache[news_id] = news

            msg = format_news_message(news)
            await call.message.answer(
                msg,
                reply_markup=get_news_buttons(news["link"], news_id),
                parse_mode="HTML"
            )
            
            # Добавляем задержку между сообщениями (кроме последнего)
            if i < len(news_list) - 1:
                await asyncio.sleep(1.5)  # 1.5 секунды задержки

        await call.message.answer("Выберите действие из меню:", reply_markup=get_main_menu())

    except Exception as e:
        logging.error(f"Ошибка при поиске новостей по теме {theme}: {e}")
        try:
            await call.message.edit_text(
                f"❌ Произошла ошибка при поиске новостей по теме: {theme_name}",
                reply_markup=get_main_menu(),
            )
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error).lower():
                logging.error(f"Ошибка при редактировании сообщения: {edit_error}")

@dp.callback_query(lambda call: call.data.startswith("full_"))
async def show_full_article(call: CallbackQuery):
    news_id = call.data.split("_", 1)[1]

    if news_id not in news_cache:
        await call.answer("❌ Новость не найдена. Попробуйте обновить список новостей.")
        return

    news = news_cache[news_id]
    await call.answer("📖 Загружаю полную статью...")

    loading_msg = await call.message.answer("📖 Загружаю полную статью...")

    try:
        result = parser.parse_full_article(news["link"])

        if result["success"]:
            await loading_msg.delete()

            full_text = result["content"]
            title = clean_html(result.get("title", news.get("title", "")))

            if len(full_text) > 4000:
                parts = []
                while full_text:
                    part = full_text[:4000]
                    last_space = part.rfind(" ")
                    if last_space != -1 and len(full_text) > 4000:
                        part = full_text[:last_space]
                        full_text = full_text[last_space:].strip()
                    else:
                        full_text = ""
                    parts.append(part)

                # Отправляем первую часть с кнопками
                await call.message.answer(
                    f"📖 <b>{title}</b>\n\n{parts[0]}",
                    parse_mode="HTML",
                    reply_markup=get_full_article_buttons(news["link"]),
                )

                # Отправляем остальные части без кнопок
                for i, part in enumerate(parts[1:], 1):
                    await call.message.answer(part, parse_mode="HTML")
                    # Добавляем задержку между частями (кроме последней)
                    if i < len(parts) - 1:
                        await asyncio.sleep(1.5)  # 1.5 секунды задержки
            else:
                await call.message.answer(
                    f"📖 <b>{title}</b>\n\n{full_text}",
                    parse_mode="HTML",
                    reply_markup=get_full_article_buttons(news["link"]),
                )
        else:
            try:
                await loading_msg.edit_text(f"❌ {result['error']}")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e

    except Exception as e:
        logging.error(f"Ошибка при загрузке полной статьи: {e}")
        try:
            await loading_msg.edit_text("❌ Произошла ошибка при загрузке статьи.")
        except Exception as edit_error:
            if "message is not modified" not in str(edit_error).lower():
                logging.error(f"Ошибка при редактировании сообщения: {edit_error}")

@dp.callback_query(lambda call: call.data.startswith("tldr_"))
async def tldr_callback(call: CallbackQuery):
    news_id = call.data.split("_", 1)[1]
    if news_id not in news_cache:
        await call.answer("❌ Новость не найдена.")
        return
    news = news_cache[news_id]
    title = clean_html(news.get('title', ''))
    base_text = news.get('text') or news.get('summary') or title
    summary = summarize_text(base_text, max_sentences=3)
    await call.message.answer(
        f"📝 <b>Кратко:</b> {summary}",
        parse_mode="HTML",
        reply_markup=get_post_action_buttons(news.get('link', ''), news_id)
    )
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("save_"))
async def save_news_callback(call: CallbackQuery):
    news_id = call.data.split("_", 1)[1]

    if news_id not in news_cache:
        await call.answer("❌ Новость не найдена для сохранения.")
        return

    try:
        news = news_cache[news_id]
        save_news(call.from_user.id, news["title"], news["link"])
        await call.answer("✅ Новость сохранена в избранное!")
    except Exception as e:
        logging.error(f"Ошибка при сохранении новости: {e}")
        await call.answer("❌ Ошибка при сохранении новости.")

@dp.message(lambda message: message.text == "⭐ Избранное")
async def show_favorites(message: Message):
    try:
        favorites = get_favorites(message.from_user.id)
        msg = format_favorites_list(favorites)
        await message.answer(msg, parse_mode="HTML", reply_markup=get_main_menu())
    except Exception as e:
        logging.error(f"Ошибка при получении избранного: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении избранного.",
            reply_markup=get_main_menu(),
        )

@dp.message(Command("export_fav"))
async def export_favorites(message: Message):
    try:
        favorites = get_favorites(message.from_user.id)
        if not favorites:
            await message.answer("У вас нет сохранённых новостей для экспорта.")
            return
        # Готовим Markdown экспорт
        lines = ["# Избранное\n"]
        for i, (title, url) in enumerate(favorites, 1):
            clean_title = clean_html(title)
            lines.append(f"{i}. [{clean_title}]({url})")
        content = "\n".join(lines)
        await message.answer_document(
            document=types.BufferedInputFile(content.encode('utf-8'), filename="favorites.md"),
            caption="Экспорт избранного (Markdown)"
        )
    except Exception as e:
        logging.error(f"Ошибка экспорта избранного: {e}")
        await message.answer("❌ Ошибка при экспорте избранного.")

@dp.message(Command("digest"))
async def one_time_digest(message: Message):
    try:
        include_keys, exclude_keys = get_user_filters(message.from_user.id)
        per_batch = get_user_news_count(message.from_user.id)
        channels = get_user_channels(message.from_user.id)
        all_posts = []
        for channel_url in channels[:5]:
            try:
                posts = tg_parser.parse_channel(channel_url, 50)
                all_posts.extend(posts)
            except Exception:
                continue
        # Простая сортировка по дате и фильтрация
        all_posts.sort(key=lambda x: x.get('date', ''), reverse=True)
        filtered = apply_filters(all_posts, include_keys, exclude_keys)[: per_batch * 3]
        if not filtered:
            await message.answer("Не найдено постов для дайджеста по текущим фильтрам.")
            return
        await message.answer(f"📰 Дайджест: {len(filtered)} постов")
        for idx, post in enumerate(filtered):
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
                    await message.answer_photo(post['image_url'], caption=caption, parse_mode="HTML")
                else:
                    await message.answer(caption, parse_mode="HTML")
                if idx < len(filtered) - 1:
                    await asyncio.sleep(1.2)
            except Exception as e:
                logging.error(f"Ошибка при отправке поста в дайджесте: {e}")
                continue
    except Exception as e:
        logging.error(f"Ошибка формирования дайджеста: {e}")
        await message.answer("❌ Ошибка при формировании дайджеста.")

@dp.message(lambda message: message.text == "📈 Статистика")
async def show_statistics(message: Message):
    try:
        await message.answer(
            "📊 <b>Статистика</b>\n\nВыберите тип статистики:",
            parse_mode="HTML",
            reply_markup=get_statistics_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе статистики: {e}")
        await message.answer("❌ Ошибка при загрузке статистики.")

@dp.message(lambda message: message.text == "🔔 Уведомления")
async def show_notifications(message: Message):
    try:
        notifications = get_unread_notifications(message.from_user.id)
        if not notifications:
            await message.answer(
                "🔔 <b>Уведомления</b>\n\nУ вас нет непрочитанных уведомлений.",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            return
        
        # Показываем первое уведомление
        notification = notifications[0]
        formatted = format_notification_message(notification)
        
        # Создаем клавиатуру для навигации по уведомлениям
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Прочитано", callback_data=f"notif_read_{notification['id']}")],
                [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"notif_delete_{notification['id']}")],
                [InlineKeyboardButton(text="⬅️ Предыдущее", callback_data=f"notif_prev_{notification['id']}")],
                [InlineKeyboardButton(text="➡️ Следующее", callback_data=f"notif_next_{notification['id']}")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
            ]
        )
        
        await message.answer(
            formatted,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Ошибка при показе уведомлений: {e}")
        await message.answer("❌ Ошибка при загрузке уведомлений.")

@dp.message(Command("recs"))
async def get_recommendations_command(message: Message):
    """Команда для получения персонализированных рекомендаций."""
    try:
        await message.answer(
            "🤖 <b>Персонализированные рекомендации</b>\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=get_recommendations_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе рекомендаций: {e}")
        await message.answer("❌ Ошибка при загрузке рекомендаций.")

@dp.message(Command("archive"))
async def show_archive(message: Message):
    """Команда для работы с архивом постов."""
    try:
        await message.answer(
            "📚 <b>Архив постов</b>\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=get_archive_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе архива: {e}")
        await message.answer("❌ Ошибка при загрузке архива.")

@dp.message(Command("search_advanced"))
async def advanced_search(message: Message):
    """Команда для расширенного поиска."""
    try:
        await message.answer(
            "🔍 <b>Расширенный поиск</b>\n\nВыберите тип поиска:",
            parse_mode="HTML",
            reply_markup=get_search_advanced_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе расширенного поиска: {e}")
        await message.answer("❌ Ошибка при загрузке расширенного поиска.")

@dp.callback_query(lambda call: call.data == "back_to_main")
async def back_to_main_callback(call: CallbackQuery):
    try:
        await call.message.delete()
    except:
        pass
    
    await call.message.answer(
        "Выберите действие из меню:",
        reply_markup=get_main_menu()
    )
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_main_from_article")
async def back_to_main_from_article_callback(call: CallbackQuery):
    try:
        await call.message.delete()
    except:
        pass
    
    await call.message.answer(
        "Выберите действие из меню:",
        reply_markup=get_main_menu()
    )
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("stats_"))
async def statistics_callback(call: CallbackQuery):
    """Обработчик для различных типов статистики."""
    try:
        stats_type = call.data.split("_")[1]
        
        if stats_type == "general":
            await show_general_statistics(call)
        elif stats_type == "activity":
            await show_activity_statistics(call)
        elif stats_type == "tags":
            await show_tags_statistics(call)
        elif stats_type == "sources":
            await show_sources_statistics(call)
        elif stats_type == "export":
            await show_export_options(call)
        else:
            await call.answer("Неизвестный тип статистики")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике статистики: {e}")
        await call.answer("❌ Ошибка при загрузке статистики")

async def show_general_statistics(call: CallbackQuery):
    """Показывает общую статистику пользователя."""
    try:
        user_stats = get_user_stats(call.from_user.id)
        summary = generate_activity_summary(user_stats)
        
        await call.message.edit_text(
            summary,
            parse_mode="HTML",
            reply_markup=get_statistics_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе общей статистики: {e}")
        await call.answer("❌ Ошибка при загрузке статистики")

async def show_activity_statistics(call: CallbackQuery):
    """Показывает статистику активности по дням и часам."""
    try:
        # Здесь можно добавить детальную статистику по времени
        await call.message.edit_text(
            "📈 <b>Статистика активности</b>\n\n"
            "Функция в разработке. Скоро здесь будет детальная статистика по дням и часам.",
            parse_mode="HTML",
            reply_markup=get_statistics_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе статистики активности: {e}")
        await call.answer("❌ Ошибка при загрузке статистики")

async def show_tags_statistics(call: CallbackQuery):
    """Показывает статистику по тегам."""
    try:
        popular_tags = get_popular_tags(10)
        if not popular_tags:
            await call.message.edit_text(
                "🏷️ <b>Популярные теги</b>\n\n"
                "Пока нет данных о популярных тегах.",
                parse_mode="HTML",
                reply_markup=get_statistics_buttons()
            )
            return
        
        tags_text = "🏷️ <b>Популярные теги:</b>\n\n"
        for i, tag in enumerate(popular_tags, 1):
            tags_text += f"{i}. {tag['name']}: {tag['usage_count']} использований\n"
        
        await call.message.edit_text(
            tags_text,
            parse_mode="HTML",
            reply_markup=get_statistics_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе статистики тегов: {e}")
        await call.answer("❌ Ошибка при загрузке статистики")

async def show_sources_statistics(call: CallbackQuery):
    """Показывает статистику по источникам."""
    try:
        user_stats = get_user_stats(call.from_user.id)
        favorite_sources = user_stats.get('favorite_sources', [])
        
        if not favorite_sources:
            await call.message.edit_text(
                "📱 <b>Популярные источники</b>\n\n"
                "У вас пока нет данных о популярных источниках.",
                parse_mode="HTML",
                reply_markup=get_statistics_buttons()
            )
            return
        
        sources_text = "📱 <b>Ваши любимые источники:</b>\n\n"
        for i, (source, count) in enumerate(favorite_sources, 1):
            sources_text += f"{i}. {source}: {count} постов\n"
        
        await call.message.edit_text(
            sources_text,
            parse_mode="HTML",
            reply_markup=get_statistics_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе статистики источников: {e}")
        await call.answer("❌ Ошибка при загрузке статистики")

async def show_export_options(call: CallbackQuery):
    """Показывает опции экспорта данных."""
    try:
        await call.message.edit_text(
            "📤 <b>Экспорт данных</b>\n\n"
            "Выберите формат для экспорта ваших данных:",
            parse_mode="HTML",
            reply_markup=get_export_format_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе опций экспорта: {e}")
        await call.answer("❌ Ошибка при загрузке опций экспорта")

@dp.callback_query(lambda call: call.data.startswith("export_"))
async def export_callback(call: CallbackQuery):
    """Обработчик для экспорта данных в различных форматах."""
    try:
        export_format = call.data.split("_")[1]
        
        if export_format == "md":
            await export_data(call, "markdown")
        elif export_format == "csv":
            await export_data(call, "csv")
        elif export_format == "json":
            await export_data(call, "json")
        elif export_format == "txt":
            await export_data(call, "text")
        else:
            await call.answer("Неизвестный формат экспорта")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике экспорта: {e}")
        await call.answer("❌ Ошибка при экспорте данных")

async def export_data(call: CallbackQuery, format_type: str):
    """Экспортирует данные пользователя в указанном формате."""
    try:
        user_id = call.from_user.id
        
        # Получаем данные для экспорта
        favorites = get_favorites(user_id)
        user_stats = get_user_stats(user_id)
        view_history = get_view_history(user_id, 100)  # Получаем реальную историю просмотров
        
        # Генерируем контент в нужном формате
        if format_type == "markdown":
            content = export_to_markdown(favorites, view_history, user_stats)
            filename = "export.md"
            mime_type = "text/markdown"
        elif format_type == "csv":
            content = export_to_csv(favorites, view_history, user_stats)
            filename = "export.csv"
            mime_type = "text/csv"
        elif format_type == "json":
            content = export_to_json(favorites, view_history, user_stats)
            filename = "export.json"
            mime_type = "application/json"
        elif format_type == "text":
            content = export_to_markdown(favorites, view_history, user_stats)  # Используем markdown как текст
            filename = "export.txt"
            mime_type = "text/plain"
        else:
            await call.answer("❌ Неподдерживаемый формат экспорта")
            return
        
        # Отправляем файл
        await call.message.answer_document(
            document=types.BufferedInputFile(
                content.encode('utf-8'), 
                filename=filename
            ),
            caption=f"📤 Экспорт данных ({format_type.upper()})"
        )
        
        # Записываем в историю экспорта
        add_export_record(user_id, format_type, len(content.encode('utf-8')))
        
        await call.answer("✅ Экспорт завершен!")
        
    except Exception as e:
        logging.error(f"Ошибка при экспорте данных: {e}")
        await call.answer("❌ Ошибка при экспорте данных")

@dp.callback_query(lambda call: call.data == "schedule_digest")
async def schedule_digest_callback(call: CallbackQuery):
    """Показывает меню настройки расписания дайджестов."""
    try:
        schedule = get_digest_schedule(call.from_user.id)
        status = "✅ Включен" if schedule['is_active'] else "❌ Отключен"
        time_str = schedule['time'] if schedule['time'] else "Не установлено"
        days_str = ", ".join(schedule['days']) if schedule['days'] else "Все дни"
        
        await call.message.edit_text(
            f"📅 <b>Расписание дайджестов</b>\n\n"
            f"Статус: {status}\n"
            f"Время: {time_str}\n"
            f"Дни: {days_str}\n\n"
            f"Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_digest_schedule_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе расписания дайджестов: {e}")
        await call.answer("❌ Ошибка при загрузке расписания")

@dp.callback_query(lambda call: call.data == "digest_set_time")
async def digest_set_time_callback(call: CallbackQuery):
    """Показывает выбор времени для дайджеста."""
    try:
        await call.message.edit_text(
            "⏰ <b>Выберите время для дайджеста</b>\n\n"
            "В какое время вы хотите получать ежедневные дайджесты?",
            parse_mode="HTML",
            reply_markup=get_time_selection_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при настройке времени дайджеста: {e}")
        await call.answer("❌ Ошибка при настройке времени")

@dp.callback_query(lambda call: call.data.startswith("time_"))
async def time_selection_callback(call: CallbackQuery):
    """Обрабатывает выбор времени для дайджеста."""
    try:
        time_str = call.data.split("_")[1]
        user_id = call.from_user.id
        
        # Получаем текущее расписание
        schedule = get_digest_schedule(user_id)
        current_days = schedule.get('days', [])
        
        # Обновляем время
        set_digest_schedule(user_id, time_str, current_days, True)
        
        await call.message.edit_text(
            f"✅ <b>Время дайджеста установлено!</b>\n\n"
            f"Теперь вы будете получать дайджесты в {time_str}\n\n"
            f"Хотите настроить дни недели?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📅 Настроить дни", callback_data="digest_set_days")],
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="schedule_digest")],
                ]
            )
        )
    except Exception as e:
        logging.error(f"Ошибка при установке времени дайджеста: {e}")
        await call.answer("❌ Ошибка при установке времени")

@dp.callback_query(lambda call: call.data == "digest_set_days")
async def digest_set_days_callback(call: CallbackQuery):
    """Показывает выбор дней недели для дайджеста."""
    try:
        await call.message.edit_text(
            "📅 <b>Выберите дни недели</b>\n\n"
            "В какие дни вы хотите получать дайджесты?",
            parse_mode="HTML",
            reply_markup=get_days_selection_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при настройке дней дайджеста: {e}")
        await call.answer("❌ Ошибка при настройке дней")

@dp.callback_query(lambda call: call.data.startswith("day_"))
async def day_selection_callback(call: CallbackQuery):
    """Обрабатывает выбор дней недели для дайджеста."""
    try:
        day_code = call.data.split("_")[1]
        user_id = call.from_user.id
        
        # Получаем текущее расписание
        schedule = get_digest_schedule(user_id)
        current_time = schedule.get('time', '09:00')
        current_days = schedule.get('days', [])
        
        # Добавляем или убираем день
        if day_code == "all":
            new_days = []  # Пустой список означает "все дни"
        elif day_code in current_days:
            new_days = [d for d in current_days if d != day_code]
        else:
            new_days = current_days + [day_code]
        
        # Обновляем расписание
        set_digest_schedule(user_id, current_time, new_days, True)
        
        days_str = ", ".join(new_days) if new_days else "Все дни"
        await call.message.edit_text(
            f"✅ <b>Дни дайджеста обновлены!</b>\n\n"
            f"Теперь вы будете получать дайджесты:\n"
            f"⏰ Время: {current_time}\n"
            f"📅 Дни: {days_str}\n\n"
            f"Расписание активно!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="schedule_digest")],
                ]
            )
        )
    except Exception as e:
        logging.error(f"Ошибка при установке дней дайджеста: {e}")
        await call.answer("❌ Ошибка при установке дней")

@dp.callback_query(lambda call: call.data == "digest_enable")
async def digest_enable_callback(call: CallbackQuery):
    """Включает автоматические дайджесты."""
    try:
        user_id = call.from_user.id
        schedule = get_digest_schedule(user_id)
        
        if not schedule.get('time'):
            await call.answer("❌ Сначала установите время для дайджеста!")
            return
        
        # Включаем дайджесты
        set_digest_schedule(user_id, schedule['time'], schedule.get('days', []), True)
        
        await call.answer("✅ Автоматические дайджесты включены!")
        
        # Обновляем сообщение
        await call.message.edit_text(
            f"📅 <b>Расписание дайджестов</b>\n\n"
            f"Статус: ✅ Включен\n"
            f"Время: {schedule['time']}\n"
            f"Дни: {', '.join(schedule.get('days', [])) or 'Все дни'}\n\n"
            f"Теперь вы будете получать дайджесты автоматически!",
            parse_mode="HTML",
            reply_markup=get_digest_schedule_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при включении дайджестов: {e}")
        await call.answer("❌ Ошибка при включении дайджестов")

@dp.callback_query(lambda call: call.data == "digest_disable")
async def digest_disable_callback(call: CallbackQuery):
    """Отключает автоматические дайджесты."""
    try:
        user_id = call.from_user.id
        schedule = get_digest_schedule(user_id)
        
        # Отключаем дайджесты
        set_digest_schedule(user_id, schedule.get('time', '09:00'), schedule.get('days', []), False)
        
        await call.answer("❌ Автоматические дайджесты отключены!")
        
        # Обновляем сообщение
        await call.message.edit_text(
            f"📅 <b>Расписание дайджестов</b>\n\n"
            f"Статус: ❌ Отключен\n"
            f"Время: {schedule.get('time', 'Не установлено')}\n"
            f"Дни: {', '.join(schedule.get('days', [])) or 'Все дни'}\n\n"
            f"Дайджесты отключены. Используйте /digest для получения вручную.",
            parse_mode="HTML",
            reply_markup=get_digest_schedule_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при отключении дайджестов: {e}")
        await call.answer("❌ Ошибка при отключении дайджестов")

@dp.callback_query(lambda call: call.data == "digest_test")
async def digest_test_callback(call: CallbackQuery):
    """Отправляет тестовый дайджест."""
    try:
        await call.answer("📰 Отправляю тестовый дайджест...")
        await scheduler.send_instant_digest(call.from_user.id)
    except Exception as e:
        logging.error(f"Ошибка при отправке тестового дайджеста: {e}")
        await call.answer("❌ Ошибка при отправке тестового дайджеста")

@dp.callback_query(lambda call: call.data.startswith("rate_"))
async def rating_callback(call: CallbackQuery):
    """Обработчик для рейтингов постов."""
    try:
        if call.data == "rate_cancel":
            await call.answer("❌ Оценка отменена")
            return
        
        # Парсим данные рейтинга
        parts = call.data.split("_")
        if len(parts) >= 3:
            post_id = parts[1]
            rating = int(parts[2])
            
            if 1 <= rating <= 5:
                # Сохраняем рейтинг
                add_post_rating(call.from_user.id, post_id, rating)
                await call.answer(f"✅ Оценка {rating}⭐ сохранена!")
            else:
                await call.answer("❌ Неверная оценка")
        else:
            await call.answer("❌ Ошибка в данных рейтинга")
            
    except Exception as e:
        logging.error(f"Ошибка при обработке рейтинга: {e}")
        await call.answer("❌ Ошибка при сохранении рейтинга")

@dp.callback_query(lambda call: call.data.startswith("comment_"))
async def comment_callback(call: CallbackQuery):
    """Обработчик для комментариев к постам."""
    try:
        action = call.data.split("_")[1]
        post_id = call.data.split("_")[2] if len(call.data.split("_")) > 2 else None
        
        if action == "add" and post_id:
            # Запрашиваем ввод комментария
            await call.message.answer(
                "💬 <b>Добавить комментарий</b>\n\n"
                "Введите ваш комментарий к посту:",
                parse_mode="HTML"
            )
            # Сохраняем post_id в состоянии
            await call.answer("Введите комментарий в следующем сообщении")
            # Здесь нужно сохранить post_id в состоянии FSM
            
        elif action == "show" and post_id:
            # Показываем комментарии к посту
            comments = get_post_comments(post_id)
            if not comments:
                await call.answer("💬 К этому посту пока нет комментариев")
                return
            
            comments_text = "💬 <b>Комментарии к посту:</b>\n\n"
            for i, comment in enumerate(comments, 1):
                username = comment['username']
                text = comment['comment']
                rating = "⭐" * comment['rating'] if comment['rating'] > 0 else ""
                date = comment['created_at']
                
                comments_text += f"{i}. <b>{username}</b> {rating}\n"
                comments_text += f"   {text}\n"
                comments_text += f"   📅 {date}\n\n"
            
            await call.message.answer(
                comments_text,
                parse_mode="HTML"
            )
        else:
            await call.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logging.error(f"Ошибка при обработке комментария: {e}")
        await call.answer("❌ Ошибка при обработке комментария")

@dp.callback_query(lambda call: call.data.startswith("recs_"))
async def recommendations_callback(call: CallbackQuery):
    """Обработчик для рекомендаций."""
    try:
        action = call.data.split("_")[1]
        
        if action == "get":
            await get_user_recommendations(call)
        elif action == "settings":
            await show_recommendations_settings(call)
        elif action == "history":
            await show_recommendations_history(call)
        else:
            await call.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике рекомендаций: {e}")
        await call.answer("❌ Ошибка при загрузке рекомендаций")

async def get_user_recommendations(call: CallbackQuery):
    """Получает и показывает рекомендации для пользователя."""
    try:
        user_id = call.from_user.id
        
        # Получаем рекомендации
        recommendations = get_recommendations(user_id, 5)
        
        if not recommendations:
            await call.message.edit_text(
                "🤖 <b>Персонализированные рекомендации</b>\n\n"
                "У нас пока недостаточно данных для формирования рекомендаций.\n"
                "Попробуйте просмотреть больше постов и оценить их!",
                parse_mode="HTML",
                reply_markup=get_recommendations_buttons()
            )
            return
        
        # Показываем рекомендации
        recs_text = "🤖 <b>Персонализированные рекомендации:</b>\n\n"
        for i, rec in enumerate(recommendations, 1):
            title = clean_html(rec['title'])
            reason = rec['reason']
            score = rec['score']
            
            recs_text += f"{i}. <b>{title}</b>\n"
            recs_text += f"   💡 {reason}\n"
            recs_text += f"   📊 Оценка: {score}\n\n"
        
        await call.message.edit_text(
            recs_text,
            parse_mode="HTML",
            reply_markup=get_recommendations_buttons()
        )
        
    except Exception as e:
        logging.error(f"Ошибка при получении рекомендаций: {e}")
        await call.answer("❌ Ошибка при загрузке рекомендаций")

async def show_recommendations_settings(call: CallbackQuery):
    """Показывает настройки рекомендаций."""
    try:
        await call.message.edit_text(
            "⚙️ <b>Настройки рекомендаций</b>\n\n"
            "Функция в разработке. Скоро здесь будут настройки для персонализации рекомендаций.",
            parse_mode="HTML",
            reply_markup=get_recommendations_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе настроек рекомендаций: {e}")
        await call.answer("❌ Ошибка при загрузке настроек")

async def show_recommendations_history(call: CallbackQuery):
    """Показывает историю рекомендаций."""
    try:
        await call.message.edit_text(
            "📊 <b>История рекомендаций</b>\n\n"
            "Функция в разработке. Скоро здесь будет история ваших рекомендаций.",
            parse_mode="HTML",
            reply_markup=get_recommendations_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе истории рекомендаций: {e}")
        await call.answer("❌ Ошибка при загрузке истории")

@dp.callback_query(lambda call: call.data.startswith("notif_"))
async def notification_callback(call: CallbackQuery):
    """Обработчик для уведомлений."""
    try:
        action = call.data.split("_")[1]
        notification_id = int(call.data.split("_")[2]) if len(call.data.split("_")) > 2 else None
        
        if action == "read" and notification_id:
            # Отмечаем уведомление как прочитанное
            mark_notification_read(notification_id)
            await call.answer("✅ Уведомление отмечено как прочитанное")
            
            # Показываем следующее уведомление или возвращаемся в меню
            await show_next_notification(call)
            
        elif action == "delete" and notification_id:
            # Удаляем уведомление
            delete_notification(notification_id)
            await call.answer("🗑️ Уведомление удалено")
            
            # Показываем следующее уведомление или возвращаемся в меню
            await show_next_notification(call)
            
        elif action == "prev" and notification_id:
            # Показываем предыдущее уведомление
            await show_previous_notification(call, notification_id)
            
        elif action == "next" and notification_id:
            # Показываем следующее уведомление
            await show_next_notification(call, notification_id)
            
        else:
            await call.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике уведомлений: {e}")
        await call.answer("❌ Ошибка при обработке уведомления")

async def show_next_notification(call: CallbackQuery, current_id: int = None):
    """Показывает следующее уведомление."""
    try:
        user_id = call.from_user.id
        notifications = get_unread_notifications(user_id)
        
        if not notifications:
            await call.message.edit_text(
                "🔔 <b>Уведомления</b>\n\nУ вас нет непрочитанных уведомлений.",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            return
        
        # Находим следующее уведомление
        if current_id:
            current_index = next((i for i, n in enumerate(notifications) if n['id'] == current_id), -1)
            next_index = (current_index + 1) % len(notifications)
        else:
            next_index = 0
        
        notification = notifications[next_index]
        formatted = format_notification_message(notification)
        
        # Создаем клавиатуру для навигации
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Прочитано", callback_data=f"notif_read_{notification['id']}")],
                [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"notif_delete_{notification['id']}")],
                [InlineKeyboardButton(text="⬅️ Предыдущее", callback_data=f"notif_prev_{notification['id']}")],
                [InlineKeyboardButton(text="➡️ Следующее", callback_data=f"notif_next_{notification['id']}")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
            ]
        )
        
        await call.message.edit_text(
            formatted,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Ошибка при показе следующего уведомления: {e}")
        await call.answer("❌ Ошибка при загрузке уведомления")

async def show_previous_notification(call: CallbackQuery, current_id: int):
    """Показывает предыдущее уведомление."""
    try:
        user_id = call.from_user.id
        notifications = get_unread_notifications(user_id)
        
        if not notifications:
            await call.message.edit_text(
                "🔔 <b>Уведомления</b>\n\nУ вас нет непрочитанных уведомлений.",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            return
        
        # Находим предыдущее уведомление
        current_index = next((i for i, n in enumerate(notifications) if n['id'] == current_id), 0)
        prev_index = (current_index - 1) % len(notifications)
        
        notification = notifications[prev_index]
        formatted = format_notification_message(notification)
        
        # Создаем клавиатуру для навигации
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Прочитано", callback_data=f"notif_read_{notification['id']}")],
                [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"notif_delete_{notification['id']}")],
                [InlineKeyboardButton(text="⬅️ Предыдущее", callback_data=f"notif_prev_{notification['id']}")],
                [InlineKeyboardButton(text="➡️ Следующее", callback_data=f"notif_next_{notification['id']}")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="back_to_main")],
            ]
        )
        
        await call.message.edit_text(
            formatted,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Ошибка при показе предыдущего уведомления: {e}")
        await call.answer("❌ Ошибка при загрузке уведомления")

# Восстанавливаем удаленные обработчики настроек
@dp.message(lambda message: message.text == "⚙️ Настройки")
async def show_settings(message: Message):
    user_channels = get_user_channels(message.from_user.id)
    news_count = get_user_news_count(message.from_user.id)
    include_keys, exclude_keys = get_user_filters(message.from_user.id)

    channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
    if len(user_channels) > 10:
        channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
    if not channels_list:
        channels_list = "У вас пока нет добавленных каналов"

    filters_text = (
        f"Включающие: {', '.join(include_keys) if include_keys else '—'}\n"
        f"Исключающие: {', '.join(exclude_keys) if exclude_keys else '—'}"
    )

    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        f"<b>Ваши Telegram каналы для мониторинга:</b>\n{channels_list}\n\n"
        f"<b>Размер пачки:</b> {news_count}\n"
        f"<b>Фильтры:</b>\n{filters_text}",
        parse_mode="HTML",
        reply_markup=get_settings_buttons(news_count),
    )

@dp.callback_query(lambda call: call.data in ("settings_increase", "settings_decrease"))
async def settings_change_batch(call: CallbackQuery):
    current = get_user_news_count(call.from_user.id)
    if call.data.endswith("increase"):
        new_val = min(10, current + 1)
    else:
        new_val = max(1, current - 1)
    set_user_news_count(call.from_user.id, new_val)
    include_keys, exclude_keys = get_user_filters(call.from_user.id)
    user_channels = get_user_channels(call.from_user.id)
    channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
    if len(user_channels) > 10:
        channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
    if not channels_list:
        channels_list = "У вас пока нет добавленных каналов"
    filters_text = (
        f"Включающие: {', '.join(include_keys) if include_keys else '—'}\n"
        f"Исключающие: {', '.join(exclude_keys) if exclude_keys else '—'}"
    )
    try:
        await call.message.edit_text(
            "⚙️ <b>Настройки</b>\n\n"
            f"<b>Ваши Telegram каналы для мониторинга:</b>\n{channels_list}\n\n"
            f"<b>Размер пачки:</b> {new_val}\n"
            f"<b>Фильтры:</b>\n{filters_text}",
            parse_mode="HTML",
            reply_markup=get_settings_buttons(new_val),
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise e
    await call.answer()

@dp.callback_query(lambda call: call.data == "settings_clear_filters")
async def settings_clear_filters(call: CallbackQuery):
    set_user_filters(call.from_user.id, [], [])
    await settings_change_batch(call)

@dp.callback_query(lambda call: call.data in ("settings_edit_include", "settings_edit_exclude"))
async def settings_edit_filters(call: CallbackQuery, state: FSMContext):
    mode = 'include' if call.data.endswith('include') else 'exclude'
    await state.update_data(edit_filter_mode=mode)
    await call.message.answer(
        "Введите ключевые слова через запятую (пример: python, ai, вакансии).",
    )
    await call.answer()

@dp.message()
async def catch_filter_input(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get('edit_filter_mode')
    if not mode:
        return  # не наш случай
    raw = message.text or ''
    items = [x.strip() for x in raw.split(',') if x.strip()]
    include_keys, exclude_keys = get_user_filters(message.from_user.id)
    if mode == 'include':
        include_keys = items
    else:
        exclude_keys = items
    set_user_filters(message.from_user.id, include_keys, exclude_keys)
    await state.update_data(edit_filter_mode=None)
    await message.answer("✅ Фильтры обновлены.")

@dp.callback_query(lambda call: call.data == "settings_theme")
async def settings_theme_callback(call: CallbackQuery):
    """Показывает выбор темы оформления."""
    try:
        current_theme = get_user_theme(call.from_user.id)
        theme_names = {
            'light': '☀️ Светлая',
            'dark': '🌙 Темная',
            'auto': '🎨 Авто'
        }
        current_name = theme_names.get(current_theme, 'Неизвестная')
        
        await call.message.edit_text(
            f"🎨 <b>Тема оформления</b>\n\n"
            f"Текущая тема: {current_name}\n\n"
            f"Выберите новую тему:",
            parse_mode="HTML",
            reply_markup=get_theme_selection_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе тем оформления: {e}")
        await call.answer("❌ Ошибка при загрузке тем")

@dp.callback_query(lambda call: call.data.startswith("theme_"))
async def theme_selection_callback(call: CallbackQuery):
    """Обрабатывает выбор темы оформления."""
    try:
        theme = call.data.split("_")[1]
        user_id = call.from_user.id
        
        if theme in ['light', 'dark', 'auto']:
            set_user_theme(user_id, theme)
            theme_names = {
                'light': '☀️ Светлая',
                'dark': '🌙 Темная',
                'auto': '🎨 Авто'
            }
            theme_name = theme_names.get(theme, theme)
            
            await call.answer(f"✅ Тема изменена на {theme_name}")
            
            # Возвращаемся в настройки
            await show_settings_from_callback(call)
        else:
            await call.answer("❌ Неизвестная тема")
            
    except Exception as e:
        logging.error(f"Ошибка при установке темы: {e}")
        await call.answer("❌ Ошибка при установке темы")

@dp.callback_query(lambda call: call.data == "settings_notifications")
async def settings_notifications_callback(call: CallbackQuery):
    """Показывает настройки уведомлений."""
    try:
        settings = get_user_notification_settings(call.from_user.id)
        status = "✅ Включены" if settings['notifications_enabled'] else "❌ Отключены"
        
        await call.message.edit_text(
            f"🔔 <b>Настройки уведомлений</b>\n\n"
            f"Статус: {status}\n\n"
            f"Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_notification_settings_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе настроек уведомлений: {e}")
        await call.answer("❌ Ошибка при загрузке настроек")

@dp.callback_query(lambda call: call.data.startswith("notif_"))
async def notification_settings_callback(call: CallbackQuery):
    """Обрабатывает настройки уведомлений."""
    try:
        action = call.data.split("_")[1]
        user_id = call.from_user.id
        
        if action == "enable":
            set_user_notification_settings(user_id, True)
            await call.answer("✅ Уведомления включены")
            
        elif action == "disable":
            set_user_notification_settings(user_id, False)
            await call.answer("🔕 Уведомления отключены")
            
        elif action == "important":
            await call.answer("🚨 Настройки важных уведомлений в разработке")
            
        elif action == "digest":
            await call.answer("📰 Настройки дайджестов в разработке")
            
        else:
            await call.answer("❌ Неизвестное действие")
            
        # Обновляем сообщение
        await show_notification_settings_updated(call)
        
    except Exception as e:
        logging.error(f"Ошибка при настройке уведомлений: {e}")
        await call.answer("❌ Ошибка при настройке уведомлений")

async def show_notification_settings_updated(call: CallbackQuery):
    """Показывает обновленные настройки уведомлений."""
    try:
        settings = get_user_notification_settings(call.from_user.id)
        status = "✅ Включены" if settings['notifications_enabled'] else "❌ Отключены"
        
        await call.message.edit_text(
            f"🔔 <b>Настройки уведомлений</b>\n\n"
            f"Статус: {status}\n\n"
            f"Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_notification_settings_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при обновлении настроек уведомлений: {e}")

async def show_settings_from_callback(call: CallbackQuery):
    """Показывает настройки из callback (для возврата из других меню)."""
    try:
        user_id = call.from_user.id
        user_channels = get_user_channels(user_id)
        news_count = get_user_news_count(user_id)
        include_keys, exclude_keys = get_user_filters(user_id)

        channels_list = "\n".join([f"• {ch}" for ch in user_channels[:10]])
        if len(user_channels) > 10:
            channels_list += f"\n... и ещё {len(user_channels) - 10} каналов"
        if not channels_list:
            channels_list = "У вас пока нет добавленных каналов"

        filters_text = (
            f"Включающие: {', '.join(include_keys) if include_keys else '—'}\n"
            f"Исключающие: {', '.join(exclude_keys) if exclude_keys else '—'}"
        )

        await call.message.edit_text(
            "⚙️ <b>Настройки</b>\n\n"
            f"<b>Ваши Telegram каналы для мониторинга:</b>\n{channels_list}\n\n"
            f"<b>Размер пачки:</b> {news_count}\n"
            f"<b>Фильтры:</b>\n{filters_text}",
            parse_mode="HTML",
            reply_markup=get_settings_buttons(news_count),
        )
    except Exception as e:
        logging.error(f"Ошибка при показе настроек из callback: {e}")
        await call.answer("❌ Ошибка при загрузке настроек")

@dp.callback_query(lambda call: call.data.startswith("archive_"))
async def archive_callback(call: CallbackQuery):
    """Обработчик для архива постов."""
    try:
        action = call.data.split("_")[1]
        
        if action == "browse":
            await show_archive_browse(call)
        elif action == "search":
            await show_archive_search(call)
        elif action == "export":
            await show_archive_export(call)
        elif action == "clear":
            await show_archive_clear(call)
        else:
            await call.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике архива: {e}")
        await call.answer("❌ Ошибка при работе с архивом")

async def show_archive_browse(call: CallbackQuery):
    """Показывает содержимое архива."""
    try:
        await call.message.edit_text(
            "📚 <b>Архив постов</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность просматривать архивированные посты.",
            parse_mode="HTML",
            reply_markup=get_archive_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе архива: {e}")
        await call.answer("❌ Ошибка при загрузке архива")

async def show_archive_search(call: CallbackQuery):
    """Показывает поиск в архиве."""
    try:
        await call.message.edit_text(
            "🔍 <b>Поиск в архиве</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность искать в архивированных постах.",
            parse_mode="HTML",
            reply_markup=get_archive_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе поиска в архиве: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

async def show_archive_export(call: CallbackQuery):
    """Показывает экспорт архива."""
    try:
        await call.message.edit_text(
            "📤 <b>Экспорт архива</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность экспортировать архивированные посты.",
            parse_mode="HTML",
            reply_markup=get_archive_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе экспорта архива: {e}")
        await call.answer("❌ Ошибка при загрузке экспорта")

async def show_archive_clear(call: CallbackQuery):
    """Показывает очистку архива."""
    try:
        await call.message.edit_text(
            "🧹 <b>Очистка архива</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность очищать старые записи из архива.",
            parse_mode="HTML",
            reply_markup=get_archive_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе очистки архива: {e}")
        await call.answer("❌ Ошибка при загрузке очистки")

@dp.callback_query(lambda call: call.data.startswith("search_"))
async def advanced_search_callback(call: CallbackQuery):
    """Обработчик для расширенного поиска."""
    try:
        action = call.data.split("_")[1]
        
        if action == "date":
            await show_date_search(call)
        elif action == "author":
            await show_author_search(call)
        elif action == "tags":
            await show_tags_search(call)
        elif action == "combined":
            await show_combined_search(call)
        else:
            await call.answer("❌ Неизвестное действие")
            
    except Exception as e:
        logging.error(f"Ошибка в обработчике расширенного поиска: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

async def show_date_search(call: CallbackQuery):
    """Показывает поиск по дате."""
    try:
        await call.message.edit_text(
            "📅 <b>Поиск по дате</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность искать посты по дате публикации.",
            parse_mode="HTML",
            reply_markup=get_search_advanced_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе поиска по дате: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

async def show_author_search(call: CallbackQuery):
    """Показывает поиск по автору."""
    try:
        await call.message.edit_text(
            "👤 <b>Поиск по автору</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность искать посты по автору.",
            parse_mode="HTML",
            reply_markup=get_search_advanced_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе поиска по автору: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

async def show_tags_search(call: CallbackQuery):
    """Показывает поиск по тегам."""
    try:
        await call.message.edit_text(
            "🏷️ <b>Поиск по тегам</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность искать посты по тегам.",
            parse_mode="HTML",
            reply_markup=get_search_advanced_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе поиска по тегам: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

async def show_combined_search(call: CallbackQuery):
    """Показывает комбинированный поиск."""
    try:
        await call.message.edit_text(
            "🔍 <b>Комбинированный поиск</b>\n\n"
            "Функция в разработке. Скоро здесь будет возможность комбинировать различные критерии поиска.",
            parse_mode="HTML",
            reply_markup=get_search_advanced_buttons()
        )
    except Exception as e:
        logging.error(f"Ошибка при показе комбинированного поиска: {e}")
        await call.answer("❌ Ошибка при загрузке поиска")

@dp.callback_query(lambda call: call.data == "noop")
async def noop_callback(call: CallbackQuery):
    """Обработчик для кнопок без действия."""
    await call.answer()

async def main():
    init_db()
    
    # Запускаем планировщик
    try:
        await scheduler.start()
        logging.info("Планировщик новостей запущен")
    except Exception as e:
        logging.error(f"Ошибка при запуске планировщика: {e}")
    
    # Запускаем бота
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем планировщик при завершении
        await scheduler.stop()
        logging.info("Планировщик новостей остановлен")

if __name__ == "__main__":
    asyncio.run(main())