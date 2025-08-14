# database/db.py
import sqlite3
import json
import logging
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timedelta
import hashlib

# Настройка логирования для этого модуля
logger = logging.getLogger(__name__)

DB_NAME = "news_bot.db"

class Database:
    def __init__(self, db_path: str = 'database.db'):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._init_db()
        logger.info("База данных инициализирована")

    def _init_db(self):
        """Создает таблицы, если они не существуют"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                chat_id INTEGER PRIMARY KEY,
                time TEXT,
                is_active BOOLEAN DEFAULT 0,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id)
            )
        """)
        self.conn.commit()

    
DEFAULT_TELEGRAM_CHANNELS = [
    "https://t.me/tproger",
    "https://t.me/rbc_news",
    "https://t.me/lenta_ru",
    "https://t.me/ria_news",
    "https://t.me/kommersant_ru",
    "https://t.me/vedomosti",
    "https://t.me/izvestia_ru",
    "https://t.me/mk_ru",
]

def init_db():
    """Создание таблиц в базе данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Основная таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    # Настройки пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            telegram_channels TEXT,
            news_count INTEGER DEFAULT 2,
            digest_schedule TEXT,
            filters TEXT,
            include_keywords TEXT, -- JSON список
            exclude_keywords TEXT, -- JSON список
            digest_days TEXT,      -- JSON список дней недели (0-6, Пн-Вс)
            digest_time TEXT,      -- Время в формате HH:MM
            theme TEXT DEFAULT 'light', -- Тема интерфейса
            notification_settings TEXT, -- JSON настройки уведомлений
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Избранные новости
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            news_title TEXT,
            news_url TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # История отправленных постов (для дайджеста)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_link TEXT UNIQUE,
            channel_name TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # История просмотров
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS view_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_link TEXT,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            time_spent INTEGER, -- В секундах
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Статистика пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_views INTEGER DEFAULT 0,
            total_saves INTEGER DEFAULT 0,
            total_searches INTEGER DEFAULT 0,
            last_digest_sent TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # История поисковых запросов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Комментарии к постам
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_link TEXT,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Рейтинги постов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_link TEXT,
            rating INTEGER, -- 1 to 5
            rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, post_link),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Рекомендации
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_link TEXT,
            score REAL,
            recommended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_shown BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Уведомления
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT, -- 'important_news', 'digest', 'system', 'reminder'
            title TEXT,
            message TEXT,
            link TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Архив постов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archived_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_data TEXT, -- JSON с полными данными поста
            archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tags TEXT, -- JSON список тегов
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Теги
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_tags (
            post_link TEXT,
            tag_id INTEGER,
            FOREIGN KEY (tag_id) REFERENCES tags (id),
            PRIMARY KEY (post_link, tag_id)
        )
    """)

    # История экспорта
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            format TEXT, -- 'txt', 'csv'
            content_size INTEGER,
            exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    # Популярные теги (для кэширования)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS popular_tags (
            tag_name TEXT PRIMARY KEY,
            count INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Маппинг коротких токенов на длинные ссылки (для callback_data)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS link_mapping (
            token TEXT PRIMARY KEY,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    # Пробуем выполнить миграции (добавление недостающих колонок)
    migrate_db()

def migrate_db():
    """Добавляет недостающие колонки в таблицы без разрушения данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Проверяем и добавляем недостающие колонки в user_settings
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'include_keywords' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN include_keywords TEXT")
        if 'exclude_keywords' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN exclude_keywords TEXT")
        if 'digest_days' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN digest_days TEXT")
        if 'digest_time' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN digest_time TEXT")
        if 'theme' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN theme TEXT DEFAULT 'light'")
        if 'notification_settings' not in columns:
            cursor.execute("ALTER TABLE user_settings ADD COLUMN notification_settings TEXT")

        # Проверяем и добавляем недостающие колонки в users
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [info[1] for info in cursor.fetchall()]
        
        if 'username' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if 'first_name' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        if 'last_name' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
        if 'last_activity' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if 'is_active' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE")

        conn.commit()
        logger.info("Миграция БД завершена успешно.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при миграции БД: {e}")
    finally:
        conn.close()

def get_or_create_link_token(url: str) -> str:
    """Возвращает короткий токен для URL. Создает запись, если ее нет."""
    if not url:
        return ""
    token = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM link_mapping WHERE token = ?", (token,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT OR IGNORE INTO link_mapping (token, url) VALUES (?, ?)", (token, url))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении link_token: {e}")
    finally:
        conn.close()
    return token

def get_url_by_token(token: str) -> Optional[str]:
    """Возвращает URL по токену."""
    if not token:
        return None
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM link_mapping WHERE token = ?", (token,))
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при чтении link_token: {e}")
        return None
    finally:
        conn.close()

# --- Базовые функции пользователей и настроек ---

def add_user(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Добавление пользователя в базу"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, created_at, last_activity, is_active) 
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE)
        """, (telegram_id, username, first_name, last_name))
        
        # Инициализируем настройки по умолчанию, если их еще нет
        cursor.execute("""
            INSERT OR IGNORE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters, include_keywords, exclude_keywords, digest_days, digest_time, theme, notification_settings) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            telegram_id, 
                         json.dumps(DEFAULT_TELEGRAM_CHANNELS), 
             10, 
             '{}', 
            '{}',
            '[]', # include_keywords
            '[]', # exclude_keywords
            '[]', # digest_days
            '09:00', # digest_time
            'light', # theme
            json.dumps({'digest': True, 'important': True, 'system': True}) # notification_settings
        ))
        
        # Инициализируем статистику
        cursor.execute("""
            INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)
        """, (telegram_id,))
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении пользователя {telegram_id}: {e}")
    finally:
        conn.close()

def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Получение данных пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (telegram_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None
    finally:
        conn.close()

def update_user_activity(telegram_id: int):
    """Обновление времени последней активности пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?
        """, (telegram_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении активности пользователя {telegram_id}: {e}")
    finally:
        conn.close()

# В database/db.py
# В database/db.py
def get_active_users(hours: int = 24) -> List[int]:
    """Получение списка активных пользователей за последние N часов"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        time_threshold = datetime.now() - timedelta(hours=hours)
        # --- ИСПРАВЛЕНИЕ: Используем 'user_id' вместо 'id' ---
        cursor.execute("""
            SELECT user_id FROM users 
            WHERE last_activity > ? AND is_active = TRUE
        """, (time_threshold,))
        # ---
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении активных пользователей: {e}")
        return []
    finally:
        conn.close()

def get_total_users() -> int:
    """Возвращает общее количество зарегистрированных пользователей."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error as e:
        logger.error(f"Ошибка при подсчете пользователей: {e}")
        return 0
    finally:
        conn.close()

def get_all_user_ids(only_active: bool = False, active_hours: int = 24) -> List[int]:
    """Возвращает список user_id всех пользователей. Можно ограничить активными."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        if only_active:
            time_threshold = datetime.now() - timedelta(hours=active_hours)
            cursor.execute(
                """
                SELECT user_id FROM users
                WHERE last_activity > ? AND is_active = TRUE
                """,
                (time_threshold,)
            )
        else:
            cursor.execute("SELECT user_id FROM users WHERE is_active = TRUE")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        return []
    finally:
        conn.close()
# --- Настройки пользователя ---

def get_user_channels(user_id: int) -> List[str]:
    """Получение списка каналов пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT telegram_channels FROM user_settings WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                channels = json.loads(result[0])
                return channels if isinstance(channels, list) else DEFAULT_TELEGRAM_CHANNELS
            except (json.JSONDecodeError, TypeError):
                return DEFAULT_TELEGRAM_CHANNELS
        else:
            return DEFAULT_TELEGRAM_CHANNELS
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении каналов пользователя {user_id}: {e}")
        return DEFAULT_TELEGRAM_CHANNELS
    finally:
        conn.close()

def set_user_channels(user_id: int, channels: List[str]):
    """Установка списка каналов пользователя"""
    if not isinstance(channels, list):
        logger.error(f"Ошибка: channels должен быть списком, получен {type(channels)}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        channels_json = json.dumps(channels)
        cursor.execute("""
            UPDATE user_settings 
            SET telegram_channels = ?
            WHERE user_id = ?
        """, (channels_json, user_id))
        
        # Если по какой-то причине записи не было, делаем INSERT
        if cursor.rowcount == 0:
             cursor.execute("""
                INSERT OR IGNORE INTO user_settings 
                (user_id, telegram_channels, news_count, digest_schedule, filters, include_keywords, exclude_keywords, digest_days, digest_time, theme, notification_settings) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, 
                                 channels_json, 
                 10, 
                 '{}', 
                '{}',
                '[]', # include_keywords
                '[]', # exclude_keywords
                '[]', # digest_days
                '09:00', # digest_time
                'light', # theme
                json.dumps({'digest': True, 'important': True, 'system': True}) # notification_settings
            ))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при установке каналов пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_user_news_count(user_id: int) -> int:
    """Получение количества новостей для дайджеста пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT news_count FROM user_settings WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0] is not None:
            try:
                news_count = int(result[0])
                return news_count if 1 <= news_count <= 50 else 2
            except (ValueError, TypeError):
                return 2
        else:
            return 2
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении news_count для пользователя {user_id}: {e}")
        return 2
    finally:
        conn.close()

def set_user_news_count(user_id: int, news_count: int):
    """Сохранение количества новостей для дайджеста пользователя."""
    if not isinstance(news_count, int) or news_count < 1 or news_count > 50:
        logger.error(f"Ошибка: news_count должен быть целым числом от 1 до 50, получен {news_count}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE user_settings 
            SET news_count = ?
            WHERE user_id = ?
        """, (news_count, user_id))
        conn.commit()
        logger.info(f"[DEBUG] news_count для пользователя {user_id} успешно сохранен: {news_count}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении news_count для пользователя {user_id}: {e}")
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



# --- Избранное ---

def save_news(user_id: int, title: str, url: str):
    """Сохранение новости в избранное"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO favorites (user_id, news_title, news_url) VALUES (?, ?, ?)",
            (user_id, title, url)
        )
        conn.commit()
        
        # Обновляем статистику
        cursor.execute("""
            UPDATE user_stats SET total_saves = total_saves + 1 WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении новости для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_favorites(user_id: int) -> List[Tuple[str, str]]:
    """Получение избранных новостей пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT news_title, news_url FROM favorites WHERE user_id = ? ORDER BY saved_at DESC",
            (user_id,)
        )
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении избранного для пользователя {user_id}: {e}")
        return []
    finally:
        conn.close()



# --- Дайджест и расписание ---

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
                # Убедимся, что возвращаемый словарь содержит все нужные ключи
                return {
                    'is_active': schedule_data.get('is_active', False),
                    'time': schedule_data.get('time', '09:00'),
                    'days': schedule_data.get('days', [])
                }
            except json.JSONDecodeError:
                # Если JSON поврежден, возвращаем значения по умолчанию
                pass
        
        # Возвращаем значения по умолчанию, если настройки не найдены, повреждены или неверного типа
        return {
            'is_active': False,
            'time': '09:00',
            'days': []
        }
    except Exception as e:
        print(f"Ошибка при получении настроек дайджеста для пользователя {user_id}: {e}")
        # Возвращаем значения по умолчанию в случае ошибки
        return {
            'is_active': False,
            'time': '09:00',
            'days': []
        }
    finally:
        conn.close()

# В database/db.py
def set_digest_schedule(user_id: int, time: str, days: list, is_active: bool):
    """
    Сохранение настроек дайджеста для пользователя.
    """
    schedule = {
        'time': time,
        'days': days,
        'is_active': is_active
    }

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        schedule_json = json.dumps(schedule)
        # Используем INSERT OR REPLACE для обновления или вставки
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_settings 
            (user_id, telegram_channels, news_count, digest_schedule, filters, include_keywords, exclude_keywords, digest_days, digest_time, theme, notification_settings) 
            VALUES (
                ?, 
                COALESCE((SELECT telegram_channels FROM user_settings WHERE user_id = ?), ?),
                COALESCE((SELECT news_count FROM user_settings WHERE user_id = ?), 2),
                ?,
                COALESCE((SELECT filters FROM user_settings WHERE user_id = ?), '{}'),
                COALESCE((SELECT include_keywords FROM user_settings WHERE user_id = ?), '[]'),
                COALESCE((SELECT exclude_keywords FROM user_settings WHERE user_id = ?), '[]'),
                COALESCE((SELECT digest_days FROM user_settings WHERE user_id = ?), '[]'),
                COALESCE((SELECT digest_time FROM user_settings WHERE user_id = ?), '09:00'),
                COALESCE((SELECT theme FROM user_settings WHERE user_id = ?), 'light'),
                COALESCE((SELECT notification_settings FROM user_settings WHERE user_id = ?), '{}')
            )
            """,
            (user_id, user_id, json.dumps(DEFAULT_TELEGRAM_CHANNELS), user_id, schedule_json, user_id, user_id, user_id, user_id, user_id, user_id, user_id)
        )
        conn.commit()
        print(f"[DEBUG] Настройки дайджеста для пользователя {user_id} успешно сохранены: {schedule}")
    except Exception as e:
        print(f"Ошибка при сохранении настроек дайджеста для пользователя {user_id}: {e}")
    finally:
        conn.close()



# --- История просмотров и статистика ---

def add_view_history(user_id: int, post_link: str, time_spent: int = 0):
    """Добавление записи в историю просмотров."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO view_history (user_id, post_link, time_spent) VALUES (?, ?, ?)
        """, (user_id, post_link, time_spent))
        conn.commit()
        
        # Обновляем статистику
        cursor.execute("""
            UPDATE user_stats SET total_views = total_views + 1 WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении в историю просмотров для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_view_history(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Получение истории просмотров пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT post_link, viewed_at, time_spent FROM view_history 
            WHERE user_id = ? ORDER BY viewed_at DESC LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении истории просмотров для пользователя {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Получение статистики пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT total_views, total_saves, total_searches, last_digest_sent 
            FROM user_stats WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return {
            'total_views': 0, 'total_saves': 0, 'total_searches': 0, 'last_digest_sent': None
        }
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении статистики для пользователя {user_id}: {e}")
        return {
            'total_views': 0, 'total_saves': 0, 'total_searches': 0, 'last_digest_sent': None
        }
    finally:
        conn.close()

def add_search_query(user_id: int, query: str):
    """Добавление поискового запроса в историю."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO search_history (user_id, query) VALUES (?, ?)
        """, (user_id, query))
        conn.commit()
        
        # Обновляем статистику
        cursor.execute("""
            UPDATE user_stats SET total_searches = total_searches + 1 WHERE user_id = ?
        """, (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении поискового запроса для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Комментарии и рейтинги ---

def add_comment(user_id: int, post_link: str, text: str):
    """Добавление комментария к посту."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO comments (user_id, post_link, text) VALUES (?, ?, ?)
        """, (user_id, post_link, text))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении комментария для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_post_comments(post_link: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Получение комментариев к посту."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.text, c.created_at, u.username, u.first_name, u.last_name
            FROM comments c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.post_link = ?
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (post_link, limit))
        rows = cursor.fetchall()
        # Форматируем результат
        comments = []
        for row in rows:
            author = row[2] or row[3] or f"User {row[3]}" # username или first_name или user_id
            comments.append({
                'text': row[0],
                'created_at': row[1],
                'author': author
            })
        return comments
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении комментариев для поста {post_link}: {e}")
        return []
    finally:
        conn.close()

def add_post_rating(user_id: int, post_link: str, rating: int):
    """Добавление рейтинга к посту."""
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        logger.error(f"Ошибка: rating должен быть целым числом от 1 до 5, получен {rating}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO post_ratings (user_id, post_link, rating, rated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, post_link, rating))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении рейтинга для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_post_rating(post_link: str) -> Optional[float]:
    """Получение среднего рейтинга поста."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT AVG(rating) FROM post_ratings WHERE post_link = ?
        """, (post_link,))
        result = cursor.fetchone()
        return float(result[0]) if result and result[0] is not None else None
    except (sqlite3.Error, ValueError, TypeError) as e:
        logger.error(f"Ошибка при получении рейтинга для поста {post_link}: {e}")
        return None
    finally:
        conn.close()

# --- Рекомендации ---

def add_recommendation(user_id: int, post_link: str, score: float):
    """Добавление рекомендации для пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO recommendations (user_id, post_link, score, recommended_at, is_shown)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, FALSE)
        """, (user_id, post_link, score))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении рекомендации для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_recommendations(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получение невидимых рекомендаций для пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT post_link, score FROM recommendations
            WHERE user_id = ? AND is_shown = FALSE
            ORDER BY score DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        return [{'post_link': row[0], 'score': row[1]} for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении рекомендаций для пользователя {user_id}: {e}")
        return []
    finally:
        conn.close()



# --- Уведомления ---

def add_notification(user_id: int, type: str, title: str, message: str, link: str = None):
    """Добавление уведомления для пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, message, link, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, FALSE, CURRENT_TIMESTAMP)
        """, (user_id, type, title, message, link))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении уведомления для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_unread_notifications(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получение непрочитанных уведомлений пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, type, title, message, link, created_at 
            FROM notifications
            WHERE user_id = ? AND is_read = FALSE
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении уведомлений для пользователя {user_id}: {e}")
        return []
    finally:
        conn.close()

def mark_notification_read(notification_id: int, user_id: int):
    """Отметить уведомление как прочитанное."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE notifications SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (notification_id, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при отметке уведомления {notification_id} как прочитанного для пользователя {user_id}: {e}")
    finally:
        conn.close()

def delete_notification(notification_id: int, user_id: int):
    """Удалить уведомление."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM notifications WHERE id = ? AND user_id = ?
        """, (notification_id, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении уведомления {notification_id} для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Архив ---

def archive_post(user_id: int, post_data: dict, tags: List[str] = None):
    """Архивирование поста."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        post_json = json.dumps(post_data)
        tags_json = json.dumps(tags if tags else [])
        
        cursor.execute("""
            INSERT INTO archived_posts (user_id, post_data, archived_at, tags)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?)
        """, (user_id, post_json, tags_json))
        conn.commit()
    except (sqlite3.Error, TypeError) as e:
        logger.error(f"Ошибка при архивировании поста для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Теги ---

def add_tag(tag_name: str):
    """Добавление тега."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO tags (name) VALUES (?)
        """, (tag_name,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении тега {tag_name}: {e}")
    finally:
        conn.close()

def get_popular_tags(limit: int = 20) -> List[Tuple[str, int]]:
    """Получение популярных тегов."""
    # Пока просто возвращаем из кэша
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT tag_name, count FROM popular_tags
            ORDER BY count DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении популярных тегов: {e}")
        return []
    finally:
        conn.close()

# --- История экспорта ---

def add_export_record(user_id: int, format: str, content_size: int):
    """Добавление записи в историю экспорта."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO export_history (user_id, format, content_size, exported_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, format, content_size))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении записи экспорта для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Отправка постов (для избежания дублей) ---

def is_post_sent(post_link: str) -> bool:
    """Проверка, был ли пост уже отправлен"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM sent_posts WHERE post_link = ?", (post_link,))
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при проверке отправленного поста {post_link}: {e}")
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
    except sqlite3.Error as e:
        logger.error(f"Ошибка при отметке поста {post_link} как отправленного: {e}")
    finally:
        conn.close()

# --- Темы и уведомления ---

def get_user_theme(user_id: int) -> str:
    """Получение темы интерфейса пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT theme FROM user_settings WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result and result[0] else 'light'
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении темы для пользователя {user_id}: {e}")
        return 'light'
    finally:
        conn.close()

def set_user_theme(user_id: int, theme: str):
    """Сохранение темы интерфейса пользователя."""
    if theme not in ['light', 'dark']:
        logger.error(f"Ошибка: Неизвестная тема {theme}")
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE user_settings SET theme = ? WHERE user_id = ?
        """, (theme, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении темы для пользователя {user_id}: {e}")
    finally:
        conn.close()

def get_user_notification_settings(user_id: int) -> dict:
    """Получение настроек уведомлений пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT notification_settings FROM user_settings WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                settings = json.loads(result[0])
                return settings if isinstance(settings, dict) else {
                    'digest': True, 'important': True, 'system': True
                }
            except json.JSONDecodeError:
                return {'digest': True, 'important': True, 'system': True}
        else:
            return {'digest': True, 'important': True, 'system': True}
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении настроек уведомлений для пользователя {user_id}: {e}")
        return {'digest': True, 'important': True, 'system': True}
    finally:
        conn.close()

def set_user_notification_settings(user_id: int, settings: dict):
    """Сохранение настроек уведомлений пользователя."""
    if not isinstance(settings, dict):
        logger.error(f"Ошибка: settings должен быть словарем, получен {type(settings)}")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        settings_json = json.dumps(settings)
        cursor.execute("""
            UPDATE user_settings SET notification_settings = ? WHERE user_id = ?
        """, (settings_json, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении настроек уведомлений для пользователя {user_id}: {e}")
    finally:
        conn.close()

# --- Конец файла ---