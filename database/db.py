import sqlite3
import os
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import hashlib

# Исправляем импорт - указываем правильный путь
# Убираем импорт из .config, так как его там нет
# Вместо этого будем передавать TELEGRAM_CHANNELS как параметр или использовать значение по умолчанию

DB_NAME = "news_bot.db"

# Определяем значение по умолчанию прямо здесь, если нужно
DEFAULT_TELEGRAM_CHANNELS = [
    "https://t.me/tproger",
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

    # Таблица для хранения настроек пользователей
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            telegram_channels TEXT,  -- JSON список каналов
            news_count INTEGER DEFAULT 2,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """
    )

    # Таблица для хранения уже отправленных постов
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

    # Пытаемся выполнить миграции (добавление недостающих колонок)
    migrate_db()


def add_user(telegram_id: int):
    """Добавление пользователя в базу"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
        # Добавляем настройки по умолчанию
        cursor.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", 
            (telegram_id,)
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
    # Используем значение по умолчанию, определенное выше
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
                return channels if isinstance(channels, list) else DEFAULT_TELEGRAM_CHANNELS
            except:
                return DEFAULT_TELEGRAM_CHANNELS
        else:
            # Иначе возвращаем дефолтные каналы
            return DEFAULT_TELEGRAM_CHANNELS
    except Exception as e:
        print(f"Ошибка при получении каналов пользователя: {e}")
        return DEFAULT_TELEGRAM_CHANNELS
    finally:
        conn.close()


def set_user_channels(user_id: int, channels: List[str]):
    """Установка списка каналов пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        channels_json = json.dumps(channels)
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_settings (user_id, telegram_channels) 
            VALUES (?, ?)
            """,
            (user_id, channels_json)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при установке каналов пользователя: {e}")
    finally:
        conn.close()


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = cursor.fetchall()
    return any(col[1] == column for col in cols)


def migrate_db():
    """Добавляет недостающие колонки в таблицы без разрушения данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Добавляем include_keywords, exclude_keywords, news_count в user_settings при необходимости
        if not _column_exists(cursor, 'user_settings', 'include_keywords'):
            cursor.execute("ALTER TABLE user_settings ADD COLUMN include_keywords TEXT")
        if not _column_exists(cursor, 'user_settings', 'exclude_keywords'):
            cursor.execute("ALTER TABLE user_settings ADD COLUMN exclude_keywords TEXT")
        if not _column_exists(cursor, 'user_settings', 'news_count'):
            cursor.execute("ALTER TABLE user_settings ADD COLUMN news_count INTEGER DEFAULT 2")
        conn.commit()
    except Exception as e:
        print(f"Ошибка миграции БД: {e}")
    finally:
        conn.close()


def get_user_news_count(user_id: int) -> int:
    """Возвращает размер пачки постов для пользователя (по умолчанию 2)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT news_count FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row and isinstance(row[0], int):
            return max(1, min(10, row[0]))
        return 2
    except Exception as e:
        print(f"Ошибка при получении news_count: {e}")
        return 2
    finally:
        conn.close()


def set_user_news_count(user_id: int, count: int):
    """Устанавливает размер пачки постов (1..10)."""
    safe_count = max(1, min(10, int(count)))
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, news_count)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET news_count=excluded.news_count
            """,
            (user_id, safe_count)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при установке news_count: {e}")
    finally:
        conn.close()


def get_user_filters(user_id: int) -> tuple[list, list]:
    """Возвращает кортеж (include_keywords, exclude_keywords) списками строк."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT include_keywords, exclude_keywords FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        include_raw = row[0] if row else None
        exclude_raw = row[1] if row else None
        try:
            include_list = json.loads(include_raw) if include_raw else []
            exclude_list = json.loads(exclude_raw) if exclude_raw else []
        except Exception:
            include_list, exclude_list = [], []
        # Гарантируем типы
        include_list = [str(x) for x in include_list if isinstance(x, (str, int, float))]
        exclude_list = [str(x) for x in exclude_list if isinstance(x, (str, int, float))]
        return include_list, exclude_list
    except Exception as e:
        print(f"Ошибка при получении фильтров: {e}")
        return [], []
    finally:
        conn.close()


def set_user_filters(user_id: int, include_keywords: List[str], exclude_keywords: List[str]):
    """Сохраняет фильтры пользователя как JSON."""
    include_clean = [str(x).strip().lower() for x in include_keywords if str(x).strip()]
    exclude_clean = [str(x).strip().lower() for x in exclude_keywords if str(x).strip()]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, include_keywords, exclude_keywords)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              include_keywords=excluded.include_keywords,
              exclude_keywords=excluded.exclude_keywords
            """,
            (user_id, json.dumps(include_clean), json.dumps(exclude_clean))
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при сохранении фильтров: {e}")
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

def get_view_history(user_id: int, limit: int = 100) -> List[Dict]:
    """Возвращает историю просмотров пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT post_id, title, link, source, viewed_at, time_spent
            FROM view_history 
            WHERE user_id = ? 
            ORDER BY viewed_at DESC 
            LIMIT ?
            """,
            (user_id, limit)
        )
        return [
            {
                'post_id': row[0],
                'title': row[1],
                'link': row[2],
                'source': row[3],
                'viewed_at': row[4],
                'time_spent': row[5]
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()

def delete_notification(notification_id: int):
    """Удаляет уведомление."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM notifications WHERE id = ?",
            (notification_id,)
        )
        conn.commit()
    finally:
        conn.close()

def get_user_theme(user_id: int) -> str:
    """Возвращает тему оформления пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT theme FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 'light'
    finally:
        conn.close()

def set_user_theme(user_id: int, theme: str):
    """Устанавливает тему оформления пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, theme)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme
            """,
            (user_id, theme)
        )
        conn.commit()
    finally:
        conn.close()

def get_user_notification_settings(user_id: int) -> Dict:
    """Возвращает настройки уведомлений пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT notifications_enabled FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        return {
            'notifications_enabled': bool(row[0]) if row else True
        }
    finally:
        conn.close()

def set_user_notification_settings(user_id: int, enabled: bool):
    """Устанавливает настройки уведомлений пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO user_settings (user_id, notifications_enabled)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET notifications_enabled=excluded.notifications_enabled
            """,
            (user_id, enabled)
        )
        conn.commit()
    finally:
        conn.close()
