import re
from html import unescape
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import json
import csv
import io

_MD_IMAGE_PATTERN = re.compile(r'!\[([\s\S]*?)\]\(([\s\S]*?)\)', re.DOTALL)
_MD_LINK_PATTERN = re.compile(r'\[([\s\S]*?)\]\(([\s\S]*?)\)', re.DOTALL)
_MD_EMPTY_LINK_PATTERN = re.compile(r'\[\s*\]\(([\s\S]*?)\)', re.DOTALL)
_RAW_URL_PATTERN = re.compile(r'(https?://|www\.)\S+', re.IGNORECASE)
_TME_PATTERN = re.compile(r'\bt\.me/\S+', re.IGNORECASE)
_ONLY_BRACKETS_PATTERN = re.compile(r'^[\s\[\]\(\)]+$')
_MULTI_SPACES_PATTERN = re.compile(r'\s+')


def clean_html(text: str) -> str:
    """Очищает HTML теги из текста."""
    if not text:
        return ""
    
    # Удаляем HTML теги
    clean = re.sub(r'<[^>]+>', '', text)
    # Декодируем HTML сущности
    clean = unescape(clean)
    # Убираем лишние пробелы
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    return clean


def is_meaningful_text(text: str) -> bool:
    """Проверяет, содержит ли строка хоть какие-нибудь значимые символы (буквы/цифры).
    Используем, чтобы отсеять мусор вроде "[](" или пустые строки."""
    if not text:
        return False
    if _ONLY_BRACKETS_PATTERN.match(text):
        return False
    return re.search(r'[A-Za-zА-Яа-яЁё0-9]', text) is not None


def soft_clean_text(text: str) -> str:
    """Более мягкая очистка: убираем только URL/лишние пробелы, оставляя остальной текст как есть."""
    if not text:
        return ""
    text = unescape(text)
    # Удаляем явные URL (чтобы не было гиперссылок)
    text = _RAW_URL_PATTERN.sub('', text)
    text = _TME_PATTERN.sub('', text)
    # Схлопываем пробелы
    text = _MULTI_SPACES_PATTERN.sub(' ', text).strip()
    return text

def format_news_message(news: Dict) -> str:
    """Форматирует новость для отправки."""
    title = clean_html(news.get('title', 'Без заголовка'))
    summary = clean_html(news.get('summary', ''))
    
    message = f"📰 <b>{title}</b>\n\n"
    
    if summary:
        if len(summary) > 300:
            summary = summary[:300] + "..."
        message += f"💬 {summary}\n\n"
    
    message += f"🔗 <a href='{news.get('link', '')}'>Читать далее</a>"
    
    return message

def format_favorites_list(favorites: list) -> str:
    """Форматирует список избранного."""
    if not favorites:
        return "⭐ У вас пока нет сохраненных новостей."
    
    message = "⭐ <b>Ваши избранные новости:</b>\n\n"
    
    for i, (title, link) in enumerate(favorites, 1):
        clean_title = clean_html(title)
        if len(clean_title) > 80:
            clean_title = clean_title[:80] + "..."
        message += f"{i}. {clean_title}\n"
        message += f"   🔗 <a href='{link}'>Открыть</a>\n\n"
    
    return message


def summarize_text(text: str, max_sentences: int = 3) -> str:
    """Грубое суммирование: берём первые N предложений после очистки."""
    if not text:
        return ""
    clean = clean_html(text)
    # Наивное разбиение на предложения
    sentences = re.split(r'(?<=[.!?])\s+', clean)
    summary = ' '.join(sentences[:max_sentences]).strip()
    if not summary:
        summary = clean[:300] + ('...' if len(clean) > 300 else '')
    return summary


def apply_filters(items: list[dict], include: list[str], exclude: list[str]) -> list[dict]:
    """Фильтрация списка постов по включающим/исключающим ключам."""
    if not items:
        return []
    include = [k.strip().lower() for k in include if k.strip()]
    exclude = [k.strip().lower() for k in exclude if k.strip()]

    def matches(item: dict) -> bool:
        text = ' '.join([
            str(item.get('title', '')),
            str(item.get('summary', '')),
            str(item.get('text', '')),
        ]).lower()
        if exclude and any(key in text for key in exclude):
            return False
        if include:
            return any(key in text for key in include)
        return True

    return [it for it in items if matches(it)]

def analyze_user_activity(view_history: List[Dict]) -> Dict:
    """Анализирует активность пользователя и возвращает статистику."""
    if not view_history:
        return {}
    
    # Анализ по времени
    hourly_activity = {}
    daily_activity = {}
    topics = {}
    sources = {}
    
    for view in view_history:
        try:
            # Время просмотра
            view_time = datetime.fromisoformat(view['viewed_at'].replace('Z', '+00:00'))
            hour = view_time.hour
            day = view_time.strftime('%A')
            
            hourly_activity[hour] = hourly_activity.get(hour, 0) + 1
            daily_activity[day] = daily_activity.get(day, 0) + 1
            
            # Источники
            source = view.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1
            
            # Темы (простой анализ по ключевым словам)
            title = view.get('title', '').lower()
            for topic in ['python', 'javascript', 'ai', 'ml', 'web', 'mobile', 'database', 'cloud']:
                if topic in title:
                    topics[topic] = topics.get(topic, 0) + 1
                    
        except Exception:
            continue
    
    # Находим пиковые часы и дни
    peak_hour = max(hourly_activity.items(), key=lambda x: x[1])[0] if hourly_activity else 0
    peak_day = max(daily_activity.items(), key=lambda x: x[1])[0] if daily_activity else 'Unknown'
    
    return {
        'total_views': len(view_history),
        'peak_hour': peak_hour,
        'peak_day': peak_day,
        'hourly_distribution': hourly_activity,
        'daily_distribution': daily_activity,
        'favorite_topics': sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5],
        'favorite_sources': sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]
    }

def generate_recommendations(user_stats: Dict, recent_posts: List[Dict], user_filters: Tuple[List, List]) -> List[Dict]:
    """Генерирует персонализированные рекомендации для пользователя."""
    recommendations = []
    
    if not recent_posts:
        return recommendations
    
    include_keys, exclude_keys = user_filters
    
    # Анализируем интересы пользователя
    favorite_topics = user_stats.get('favorite_topics', [])
    favorite_sources = user_stats.get('favorite_sources', [])
    
    # Создаем словарь для подсчета очков
    post_scores = {}
    
    for post in recent_posts:
        score = 0
        title = post.get('title', '').lower()
        source = post.get('source', '').lower()
        
        # Бонус за любимые темы
        for topic, count in favorite_topics:
            if topic in title:
                score += count * 2
        
        # Бонус за любимые источники
        for src, count in favorite_sources:
            if src in source:
                score += count
        
        # Бонус за соответствие фильтрам
        if include_keys:
            if any(key in title for key in include_keys):
                score += 5
        
        # Штраф за исключающие слова
        if exclude_keys:
            if any(key in title for key in exclude_keys):
                score -= 10
        
        # Бонус за свежесть (если есть дата)
        if post.get('date'):
            try:
                post_date = datetime.fromisoformat(post['date'].replace('Z', '+00:00'))
                days_old = (datetime.now() - post_date).days
                if days_old <= 1:
                    score += 3
                elif days_old <= 3:
                    score += 1
            except:
                pass
        
        post_scores[post] = max(0, score)
    
    # Сортируем по очкам и берем топ
    sorted_posts = sorted(post_scores.items(), key=lambda x: x[1], reverse=True)
    
    for post, score in sorted_posts[:10]:
        if score > 0:
            reason = _generate_recommendation_reason(post, score, favorite_topics, favorite_sources)
            recommendations.append({
                'post': post,
                'score': score,
                'reason': reason
            })
    
    return recommendations

def _generate_recommendation_reason(post: Dict, score: int, favorite_topics: List, favorite_sources: List) -> str:
    """Генерирует объяснение для рекомендации."""
    reasons = []
    title = post.get('title', '').lower()
    source = post.get('source', '').lower()
    
    # Проверяем темы
    for topic, count in favorite_topics:
        if topic in title:
            reasons.append(f"ваш любимый топик '{topic}'")
    
    # Проверяем источники
    for src, count in favorite_sources:
        if src in source:
            reasons.append(f"популярный у вас источник")
    
    # Проверяем свежесть
    if post.get('date'):
        try:
            post_date = datetime.fromisoformat(post['date'].replace('Z', '+00:00'))
            days_old = (datetime.now() - post_date).days
            if days_old <= 1:
                reasons.append("свежая новость")
        except:
            pass
    
    if reasons:
        return f"Рекомендуем: {', '.join(reasons)}"
    else:
        return "Рекомендуем на основе ваших интересов"

def export_to_markdown(favorites: List[Tuple], view_history: List[Dict], user_stats: Dict) -> str:
    """Экспортирует данные в Markdown формат."""
    lines = ["# Экспорт данных из News Bot\n\n"]
    
    # Статистика
    lines.append("## 📊 Статистика\n\n")
    lines.append(f"- **Всего просмотров:** {user_stats.get('total_views', 0)}\n")
    lines.append(f"- **Всего избранного:** {user_stats.get('total_favorites', 0)}\n")
    lines.append(f"- **Всего поисков:** {user_stats.get('total_searches', 0)}\n")
    
    # Любимые темы
    if user_stats.get('favorite_topics'):
        lines.append("\n### 🏷️ Любимые темы\n\n")
        for topic, count in user_stats['favorite_topics']:
            lines.append(f"- {topic}: {count} постов\n")
    
    # Любимые источники
    if user_stats.get('favorite_sources'):
        lines.append("\n### 📱 Любимые источники\n\n")
        for source, count in user_stats['favorite_sources']:
            lines.append(f"- {source}: {count} постов\n")
    
    # Избранное
    if favorites:
        lines.append("\n## ⭐ Избранное\n\n")
        for i, (title, url) in enumerate(favorites, 1):
            clean_title = clean_html(title)
            lines.append(f"{i}. [{clean_title}]({url})\n")
    
    # История просмотров (последние 20)
    if view_history:
        lines.append("\n## 📚 История просмотров (последние 20)\n\n")
        for i, view in enumerate(view_history[-20:], 1):
            title = clean_html(view.get('title', 'Без заголовка'))
            source = view.get('source', 'Неизвестный источник')
            date = view.get('viewed_at', 'Неизвестная дата')
            lines.append(f"{i}. **{title}**\n")
            lines.append(f"   📍 Источник: {source}\n")
            lines.append(f"   📅 Дата: {date}\n\n")
    
    return "\n".join(lines)

def export_to_csv(favorites: List[Tuple], view_history: List[Dict], user_stats: Dict) -> str:
    """Экспортирует данные в CSV формат."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Статистика
    writer.writerow(['Тип данных', 'Значение'])
    writer.writerow(['Всего просмотров', user_stats.get('total_views', 0)])
    writer.writerow(['Всего избранного', user_stats.get('total_favorites', 0)])
    writer.writerow(['Всего поисков', user_stats.get('total_searches', 0)])
    writer.writerow([])
    
    # Любимые темы
    if user_stats.get('favorite_topics'):
        writer.writerow(['Тема', 'Количество постов'])
        for topic, count in user_stats['favorite_topics']:
            writer.writerow([topic, count])
        writer.writerow([])
    
    # Избранное
    if favorites:
        writer.writerow(['Заголовок', 'Ссылка'])
        for title, url in favorites:
            clean_title = clean_html(title)
            writer.writerow([clean_title, url])
        writer.writerow([])
    
    # История просмотров
    if view_history:
        writer.writerow(['Заголовок', 'Источник', 'Дата просмотра'])
        for view in view_history[-50:]:  # Последние 50
            title = clean_html(view.get('title', 'Без заголовка'))
            source = view.get('source', 'Неизвестный источник')
            date = view.get('viewed_at', 'Неизвестная дата')
            writer.writerow([title, source, date])
    
    return output.getvalue()

def export_to_json(favorites: List[Tuple], view_history: List[Dict], user_stats: Dict) -> str:
    """Экспортирует данные в JSON формат."""
    export_data = {
        'export_date': datetime.now().isoformat(),
        'statistics': user_stats,
        'favorites': [
            {
                'title': clean_html(title),
                'url': url
            }
            for title, url in favorites
        ],
        'recent_views': [
            {
                'title': clean_html(view.get('title', '')),
                'source': view.get('source', ''),
                'viewed_at': view.get('viewed_at', ''),
                'time_spent': view.get('time_spent', 0)
            }
            for view in view_history[-50:]  # Последние 50
        ]
    }
    
    return json.dumps(export_data, ensure_ascii=False, indent=2)

def extract_tags_from_text(text: str) -> List[str]:
    """Извлекает потенциальные теги из текста."""
    if not text:
        return []
    
    # Простые правила для извлечения тегов
    text_lower = text.lower()
    tags = []
    
    # Технические теги
    tech_keywords = [
        'python', 'javascript', 'java', 'c++', 'c#', 'go', 'rust', 'php', 'ruby',
        'ai', 'ml', 'machine learning', 'deep learning', 'neural network',
        'web', 'mobile', 'ios', 'android', 'react', 'vue', 'angular',
        'database', 'sql', 'nosql', 'mongodb', 'postgresql', 'mysql',
        'cloud', 'aws', 'azure', 'gcp', 'docker', 'kubernetes',
        'blockchain', 'crypto', 'bitcoin', 'ethereum',
        'cybersecurity', 'security', 'privacy', 'gdpr'
    ]
    
    for keyword in tech_keywords:
        if keyword in text_lower:
            tags.append(keyword)
    
    # Удаляем дубликаты и сортируем
    return sorted(list(set(tags)))

def calculate_reading_time(text: str) -> int:
    """Вычисляет примерное время чтения текста в минутах."""
    if not text:
        return 0
    
    # Средняя скорость чтения: 200 слов в минуту
    words = len(text.split())
    minutes = max(1, words // 200)
    
    return minutes

def format_time_spent(seconds: int) -> str:
    """Форматирует время, проведенное с постом."""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}ч {minutes}м"

def generate_activity_summary(user_stats: Dict) -> str:
    """Генерирует краткую сводку активности пользователя."""
    if not user_stats:
        return "У вас пока нет активности."
    
    total_views = user_stats.get('total_views', 0)
    total_favorites = user_stats.get('total_favorites', 0)
    total_searches = user_stats.get('total_searches', 0)
    
    summary = f"📊 <b>Ваша активность:</b>\n\n"
    summary += f"👁️ <b>Просмотров:</b> {total_views}\n"
    summary += f"⭐ <b>В избранном:</b> {total_favorites}\n"
    summary += f"🔍 <b>Поисков:</b> {total_searches}\n"
    
    if user_stats.get('favorite_topics'):
        top_topic = user_stats['favorite_topics'][0]
        summary += f"\n🏷️ <b>Любимая тема:</b> {top_topic[0]} ({top_topic[1]} постов)\n"
    
    if user_stats.get('favorite_sources'):
        top_source = user_stats['favorite_sources'][0]
        summary += f"📱 <b>Любимый источник:</b> {top_source[0]} ({top_source[1]} постов)\n"
    
    if user_stats.get('peak_hour') is not None:
        summary += f"\n⏰ <b>Пик активности:</b> {user_stats['peak_hour']}:00\n"
    
    if user_stats.get('peak_day'):
        summary += f"📅 <b>Самый активный день:</b> {user_stats['peak_day']}\n"
    
    return summary

def format_notification_message(notification: Dict) -> str:
    """Форматирует уведомление для отображения."""
    notification_type = notification.get('type', 'unknown')
    title = notification.get('title', 'Уведомление')
    message = notification.get('message', '')
    created_at = notification.get('created_at', '')
    
    # Иконки для разных типов уведомлений
    icons = {
        'important_news': '🚨',
        'digest': '📰',
        'system': '⚙️',
        'reminder': '⏰',
        'update': '🔄'
    }
    
    icon = icons.get(notification_type, '🔔')
    
    formatted = f"{icon} <b>{title}</b>\n\n{message}"
    
    if created_at:
        try:
            # Парсим время и форматируем
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            time_str = dt.strftime('%d.%m.%Y %H:%M')
            formatted += f"\n\n📅 {time_str}"
        except:
            pass
    
    return formatted