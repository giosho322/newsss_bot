# database/db.py
import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

# --- ИСПРАВЛЕНИЕ: Убираем несуществующий импорт и определяем DEFAULT_TELEGRAM_CHANNELS локально ---
DB_NAME = "news_bot.db"

# Определяем значение по умолчанию прямо здесь
# Обновленный список каналов из логов
DEFAULT_TELEGRAM_CHANNELS = [
    "https://t.me/finansist_busines",
    "https://t.me/TrendWatching24", 
    "https://t.me/bazaar_live",
    "https://t.me/habr",
    # Добавьте сюда нужные вам каналы
]

def init_db():
    """Создание таблиц в базе данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # --- ИСПРАВЛЕНИЕ: Добавляем поле digest_schedule и filters в user_settings ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            telegram_channels TEXT,     -- JSON список каналов
            news_count INTEGER DEFAULT 2,
            digest_schedule TEXT,       -- JSON настройки дайджеста
            filters TEXT,               -- НОВОЕ ПОЛЕ: JSON фильтры пользователя
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            news_title TEXT,
            news_url TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    # Таблица для хранения уже отправленных постов (для дайджеста)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_posts (
            id INTEGER PRIMARY KEY,
            post_link TEXT UNIQUE,
            channel_name TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def add_user(telegram_id: int):
    """Добавление пользователя в базу"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
        # Добавляем настройки по умолчанию
        # Обновляем INSERT OR IGNORE, чтобы не перезаписывать существующие настройки
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, json.dumps(DEFAULT_TELEGRAM_CHANNELS), 2, '{}', '{}')
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Пользователь уже существует
    finally:
        conn.close()


def save_news(user_id: int, title: str, url: str):
    """Сохранение новости в избранное"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO favorites (user_id, news_title, news_url) VALUES (?, ?, ?)",
            (user_id, title, url),
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при сохранении новости: {e}")
        raise
    finally:
        conn.close()


def get_favorites(user_id: int) -> list:
    """Получение избранных новостей пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT news_title, news_url FROM favorites 
            WHERE user_id = ? ORDER BY saved_at DESC
            """,
            (user_id,),
        )
        favorites = cursor.fetchall()
        return favorites
    except Exception as e:
        print(f"Ошибка при получении избранного: {e}")
        return []
    finally:
        conn.close()


def get_user_channels(user_id: int) -> List[str]:
    """Получение списка каналов пользователя"""
    # --- ИСПРАВЛЕНИЕ: Используем DEFAULT_TELEGRAM_CHANNELS, определенный выше ---
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT telegram_channels FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result[0]:
            # Если у пользователя есть свои каналы, возвращаем их
            try:
                channels = json.loads(result[0])
                # Проверка типа на случай, если данные повреждены
                return channels if isinstance(channels, list) else DEFAULT_TELEGRAM_CHANNELS
            except (json.JSONDecodeError, TypeError):
                # Если JSON поврежден или не список, возвращаем дефолт
                return DEFAULT_TELEGRAM_CHANNELS
        else:
            # Иначе возвращаем дефолтные каналы
            return DEFAULT_TELEGRAM_CHANNELS
    except Exception as e:
        print(f"Ошибка при получении каналов пользователя {user_id}: {e}")
        return DEFAULT_TELEGRAM_CHANNELS
    finally:
        conn.close()


def set_user_channels(user_id: int, channels: List[str]):
    """Установка списка каналов пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        channels_json = json.dumps(channels)
        # Используем INSERT OR REPLACE для обновления или вставки
        # Обновляем все поля, используя COALESCE для сохранения старых значений
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters) 
            VALUES (
                ?, 
                ?,
                COALESCE((SELECT news_count FROM user_settings WHERE user_id = ?), 2),
                COALESCE((SELECT digest_schedule FROM user_settings WHERE user_id = ?), '{}'),
                COALESCE((SELECT filters FROM user_settings WHERE user_id = ?), '{}')
            )
            """,
            (user_id, channels_json, user_id, user_id, user_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при установке каналов пользователя {user_id}: {e}")
    finally:
        conn.close()


def is_post_sent(post_link: str) -> bool:
    """Проверка, был ли пост уже отправлен"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM sent_posts WHERE post_link = ?",
            (post_link,)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Ошибка при проверке отправленного поста: {e}")
        return False
    finally:
        conn.close()


def mark_post_as_sent(post_link: str, channel_name: str):
    """Отметить пост как отправленный"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO sent_posts (post_link, channel_name) VALUES (?, ?)",
            (post_link, channel_name)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при отметке поста как отправленного: {e}")
    finally:
        conn.close()

# --- ФУНКЦИИ ДЛЯ ДАЙДЖЕСТА И ФИЛЬТРОВ ---

def get_digest_schedule(user_id: int) -> dict:
    """
    Получение настроек дайджеста для пользователя.
    Возвращает словарь с настройками.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT digest_schedule FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                schedule_data = json.loads(result[0])
                # Базовая валидация типа
                if isinstance(schedule_data, dict):
                    return schedule_data
                else:
                    print(f"Предупреждение: Некорректный формат настроек дайджеста для пользователя {user_id}")
            except json.JSONDecodeError:
                print(f"Предупреждение: Некорректный JSON настроек дайджеста для пользователя {user_id}")
                # Если JSON поврежден, возвращаем значения по умолчанию
        
        # Возвращаем значения по умолчанию, если настройки не найдены, повреждены или неверного типа
        return {
            'enabled': False,
            'frequency': 'daily', # или 'weekly'
            'time': '09:00'       # время в формате HH:MM
        }
    except Exception as e:
        print(f"Ошибка при получении настроек дайджеста для пользователя {user_id}: {e}")
        # Возвращаем значения по умолчанию в случае ошибки
        return {
            'enabled': False,
            'frequency': 'daily',
            'time': '09:00'
        }
    finally:
        conn.close()

def set_digest_schedule(user_id: int, schedule: dict):
    """
    Сохранение настроек дайджеста для пользователя.
    """
    # Базовая валидация входных данных
    if not isinstance(schedule, dict):
        print(f"Ошибка: schedule должен быть словарем, получен {type(schedule)}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        schedule_json = json.dumps(schedule)
        # Используем INSERT OR REPLACE для обновления или вставки
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters) 
            VALUES (
                ?, 
                COALESCE((SELECT telegram_channels FROM user_settings WHERE user_id = ?), ?),
                COALESCE((SELECT news_count FROM user_settings WHERE user_id = ?), 2),
                ?,
                COALESCE((SELECT filters FROM user_settings WHERE user_id = ?), '{}')
            )
            """,
            (user_id, user_id, json.dumps(DEFAULT_TELEGRAM_CHANNELS), user_id, schedule_json, user_id)
        )
        conn.commit()
        print(f"[DEBUG] Настройки дайджеста для пользователя {user_id} успешно сохранены: {schedule}")
    except Exception as e:
        print(f"Ошибка при сохранении настроек дайджеста для пользователя {user_id}: {e}")
    finally:
        conn.close()


def get_user_filters(user_id: int) -> dict:
    """
    Получение фильтров пользователя для дайджеста.
    Возвращает словарь с настройками фильтров.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT filters FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                filters_data = json.loads(result[0])
                # Базовая валидация типа
                if isinstance(filters_data, dict):
                    return filters_data
                else:
                    print(f"Предупреждение: Некорректный формат фильтров для пользователя {user_id}")
            except json.JSONDecodeError:
                print(f"Предупреждение: Некорректный JSON фильтров для пользователя {user_id}")
                # Если JSON поврежден, возвращаем пустой словарь
        
        # Возвращаем пустой словарь, если фильтры не найдены, повреждены или неверного типа
        return {}
    except Exception as e:
        print(f"Ошибка при получении фильтров для пользователя {user_id}: {e}")
        # Возвращаем пустой словарь в случае ошибки
        return {}
    finally:
        conn.close()


def set_user_filters(user_id: int, filters: dict):
    """
    Сохранение фильтров пользователя.
    """
    # Базовая валидация входных данных
    if not isinstance(filters, dict):
        print(f"Ошибка: filters должен быть словарем, получен {type(filters)}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        filters_json = json.dumps(filters)
        # Используем INSERT OR REPLACE для обновления или вставки
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters) 
            VALUES (
                ?, 
                COALESCE((SELECT telegram_channels FROM user_settings WHERE user_id = ?), ?),
                COALESCE((SELECT news_count FROM user_settings WHERE user_id = ?), 2),
                COALESCE((SELECT digest_schedule FROM user_settings WHERE user_id = ?), '{}'),
                ?
            )
            """,
            (user_id, user_id, json.dumps(DEFAULT_TELEGRAM_CHANNELS), user_id, user_id, filters_json)
        )
        conn.commit()
        print(f"[DEBUG] Фильтры для пользователя {user_id} успешно сохранены: {filters}")
    except Exception as e:
        print(f"Ошибка при сохранении фильтров для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Конец новых функций ---