# 📰 Telegram News Bot

Интеллектуальный Telegram бот для получения новостей из различных источников с возможностью настройки каналов, автоматических дайджестов и системы оценок.

## 🌟 Возможности

- **📺 Мониторинг каналов**: Автоматический парсинг новостей из Telegram каналов
- **📊 Топ новостей**: Рейтинг самых популярных постов за день
- **⚙️ Настройки**: Персонализация каналов
- **📈 Статистика**: Отслеживание активности пользователей
- **👨‍💼 Админ-панель**: Управление пользователями и рассылка сообщений

## 🚀 Быстрый старт

### Предварительные требования

- Python 3.8+
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))
- Git

### Установка

1. **Клонируйте репозиторий:**
```
git clone https://github.com/your-username/news_bot.git
cd news_bot
```

2. **Создайте виртуальное окружение:**
```
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. **Установите зависимости:**
```
pip install -r requirements.txt
```

4. **Настройте переменные окружения:**
Создайте файл `.env` в корневой папке проекта:
```
BOT_TOKEN=your_telegram_bot_token_here
```

5. **Запустите бота:**
```
python run_bot.py
```

## 📋 Требования

- **aiogram==3.4.1** - Telegram Bot API
- **feedparser==6.0.11** - Парсинг RSS лент
- **beautifulsoup4==4.12.3** - Парсинг HTML
- **requests==2.31.0** - HTTP запросы
- **lxml==5.1.0** - XML/HTML парсер
- **pytz==2024.1** - Работа с часовыми поясами

## 🏗️ Структура проекта

```
news_bot/
├── bot/                    # Основной код бота
│   ├── main.py            # Главный файл с обработчиками
│   ├── config.py          # Конфигурация
│   └── admin.py           #Админские функции
├── database/              # Работа с базой данных
│   └── db.py             # SQLite операции
├── parsers/               # Парсеры новостей
│   └── telegram_parser.py # Парсер Telegram каналов
├── run_bot.py            # Скрипт запуска
├── requirements.txt      # Зависимости
└── README.md             #Документация
```

## 🎯 Использование бота

### Основные команды

- `/start` - Запуск бота и главное меню
- `/help` - Справка по командам
- `/top` - Топ новостей за сегодня
- `/settings` - Настройки бота
- `/digest` - Получить дайджест сейчас
- `/stats` - Статистика активности
-  либо кнопками 
### Настройка каналов

1. Перейдите в **Настройки** → **Каналы**
2. Выберите интересующие вас каналы из списка

### Автодайджест

1. В **Настройках** → **Уведомления** включите автодайджест
2. Установите удобное время получения (например, 09:00)
3. Выберите дни недели для получения дайджеста
4. Бот будет автоматически отправлять дайджест в
5. 
## 🛠️ Установка на сервер

### Ubuntu/Debian

1. **Обновите систему:**
```
sudo apt update && sudo apt upgrade -y
```

2. **Установите Python и зависимости:**
```
sudo apt install python3 python3-pip python3-venv git -y
```

3. **Клонируйте проект:**
```
git clone https://github.com/your-username/news_bot.git
cd news_bot
```

4. **Создайте виртуальное окружение:**
```
python3 -m venv venv
source venv/bin/activate
```

5. **Установите зависимости:**
```
pip install -r requirements.txt
```

6. **Настройте переменные окружения:**
```
nano .env
```
Добавьте ваш токен бота:
```
BOT_TOKEN=your_telegram_bot_token_here
```

7. **Создайте systemd сервис:**
```
sudo nano /etc/systemd/system/news-bot.service
```

Содержимое файла:
```
[Unit]
Description=Telegram News Bot
After=network.target

[Service]
Type=simple
User=root     #если другое имя сервера меняй
WorkingDirectory=/root/newsss_bot
Environment=PATH=/root/newsss_bot/venv/bin
ExecStart=/root/newsss_bot/venv/bin/python /root/newsss_bot/run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

8. **Запустите сервис:**
```
sudo systemctl daemon-reload
sudo systemctl enable news-bot
sudo systemctl start news-bot
```

9. **Проверьте статус:**
```
sudo systemctl status news-bot
```

### CentOS/RHEL

1. **Установите EPEL и Python:**
```
sudo yum install epel-release -y
sudo yum install python3 python3-pip git -y
```

2. **Повторите шаги 3-9 из инструкции для Ubuntu**

### Docker (альтернативный способ)

1. **Создайте Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "run_bot.py"]
```

2. **Создайте docker-compose.yml:**
```yaml
version: '3.8'
services:
  news-bot:
    build: .
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
    restart: unless-stopped
```

3. **Запустите:**
```bash
docker-compose up -d
```

## 🔧 Конфигурация

### Настройка каналов

Отредактируйте `bot/config.py` для изменения списка каналов:

```python
TELEGRAM_CHANNELS = [
    "https://t.me/tproger",      # IT новости
    "https://t.me/rbc_news",     # РБК
    "https://t.me/lenta_ru",     # Лента.ру
    # Добавьте свои каналы
]
```
Либо через бота

### Админские функции

В файле `bot/admin.py` настройте ID администраторов:

```python
ADMIN_IDS = [1203425573]  # Замените на ваши ID
```

## 📊 Мониторинг и логи

### Просмотр логов

```bash
# Systemd сервис
sudo journalctl -u news-bot -f

# Docker
docker-compose logs -f news-bot
```

### База данных

База данных SQLite находится в файле `news_bot.db` и содержит:
- Пользователей и их настройки
- Новости и оценки
- Комментарии
- Статистику активности

## 🚨 Устранение неполадок

### Бот не запускается

1. **Проверьте токен:**
```
cat .env
```

2. **Проверьте зависимости:**
```
pip list | grep aiogram
```

3. **Проверьте логи:**
```
python run_bot.py
```

### Новости не загружаются

1. **Проверьте доступность каналов:**
```
curl -I https://t.me/tproger
```

2. **Проверьте настройки каналов в базе данных:**
```
sqlite3 news_bot.db "SELECT * FROM user_channels LIMIT 5;"
```

### Дайджест не отправляется


## 🔒 Безопасность

- Никогда не публикуйте токен бота в открытом доступе
- Используйте виртуальные окружения
- Регулярно обновляйте зависимости
- Ограничьте доступ к серверу только необходимыми портами

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request


## 📞 Поддержка

Если у вас возникли вопросы или проблемы:

1. Создайте Issue в GitHub
2. Опишите проблему подробно
3. Приложите логи ошибок
4. Укажите версию Python и ОС

## 🔄 Обновления

Для обновления бота:

```
git pull origin main
pip install -r requirements.txt
sudo systemctl restart news-bot
```

---

**Приятного использования! 📰✨**
