import logging
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === ВАЖНО: ЗАМЕНИ НА СВОИ ТОКЕНЫ ===
TELEGRAM_TOKEN = '7966480306:AAEzpDlkcU0X_iyBNB3fl5giS579XkPZKLw' # Заменить на токен от @BotFather
WEATHER_API_KEY = '16c701065dc04a0f803133330251008'   # Заменить на ключ с weatherapi.com
# ======================================

# Состояния для ConversationHandler
ASK_CITY = 1

# Храним данные пользователей (в реальном проекте лучше использовать БД)
user_data = {}

# Клавиатура
keyboard = [
    [KeyboardButton("🌤 Погода")],
    [KeyboardButton("📍 Указать город")],
    [KeyboardButton("💾 Запомнить город")]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -------------------
# Функции
# -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text(
        "👋 Привет! Я бот погоды на базе WeatherAPI!\n"
        "Нажми «📍 Указать город», чтобы ввести город.\n"
        "Или «🌤 Погода», чтобы узнать погоду в сохранённом городе.",
        reply_markup=reply_markup
    )

async def ask_for_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏙 Введи название города:")
    return ASK_CITY

async def save_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    city = update.message.text.strip()

    if not city:
        await update.message.reply_text("❌ Пожалуйста, укажи город.")
        return

    user_data[user_id]['city'] = city
    await update.message.reply_text(f"✅ Город {city} сохранён!", reply_markup=reply_markup)
    return ConversationHandler.END

async def show_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    city = user_data.get(user_id, {}).get('city')

    if not city:
        await update.message.reply_text(
            "❌ Город не задан. Нажми «📍 Указать город» или введи название вручную."
        )
        return

    await get_weather_for_city(update, city)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ['погода', '🌤 погода']:
        await show_weather(update, context)
    elif text.lower() in ['указать город', '📍 указать город']:
        await ask_for_city(update, context)
    elif text.lower() in ['запомнить город', '💾 запомнить город']:
        await save_current_city(update, context)
    else:
        await get_weather_for_city(update, text)

async def save_current_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    city = user_data.get(user_id, {}).get('temp_city')
    if city:
        user_data[user_id]['city'] = city
        await update.message.reply_text(f"✅ Город {city} теперь по умолчанию!", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Нет города для сохранения. Сначала узнай погоду.")

async def get_weather_for_city(update: Update, city: str):
    user_id = update.effective_user.id
    user_data[user_id]['temp_city'] = city # Сохраняем временно

    url = "http://api.weatherapi.com/v1/current.json"
    params = {
        'key': WEATHER_API_KEY,
        'q': city,
        'lang': 'ru' # Для русского описания погоды
    }

    try:
        logging.info(f"Запрос к WeatherAPI: {url}, params: {params}")
        response = requests.get(url, params=params, timeout=10)
        logging.info(f"Статус ответа: {response.status_code}")
        response.raise_for_status() # Вызовет исключение для HTTP ошибок (4xx или 5xx)
        data = response.json()
        logging.info(f"Данные от WeatherAPI: {data}")

        # Проверка на ошибки от API
        if 'error' in data:
             error_message = data['error'].get('message', 'Неизвестная ошибка API')
             await update.message.reply_text(
                 f"❌ Ошибка API WeatherAPI: {error_message}",
                 reply_markup=reply_markup
             )
             return

        # Извлечение данных
        location_name = data['location']['name']
        region = data['location']['region']
        country = data['location']['country']
        temp_c = data['current']['temp_c']
        feelslike_c = data['current']['feelslike_c']
        condition_text = data['current']['condition']['text']
        humidity = data['current']['humidity']
        wind_kph = data['current']['wind_kph']
        wind_dir = data['current']['wind_dir']

        # Формирование сообщения
        message = (
            f"🌍 <b>Погода в {location_name}</b>\n"
            f"<i>({region}, {country})</i>\n\n"
            f"🌡 Температура: <b>{temp_c}°C</b>\n"
            f"🌡 Ощущается как: <b>{feelslike_c}°C</b>\n"
            f"☁ Описание: <i>{condition_text}</i>\n"
            f"💧 Влажность: <b>{humidity}%</b>\n"
            f"💨 Ветер: <b>{wind_kph} км/ч</b> ({wind_dir})"
        )

        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP ошибка при запросе к WeatherAPI: {e}")
        if response.status_code == 401:
            await update.message.reply_text(
                "❌ Ошибка 401: Неверный API ключ WeatherAPI. Проверь ключ в коде.",
                reply_markup=reply_markup
            )
        elif response.status_code == 400:
             await update.message.reply_text(
                "❌ Ошибка 400: Неверный запрос (возможно, город не найден).",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"❌ HTTP ошибка {response.status_code} при обращении к WeatherAPI.",
                reply_markup=reply_markup
            )
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка сети при запросе к WeatherAPI: {e}")
        await update.message.reply_text(
            "⚠️ Ошибка сети при получении данных о погоде. Проверь подключение к интернету.",
            reply_markup=reply_markup
        )
    except KeyError as e:
        logging.error(f"Ошибка обработки данных от WeatherAPI: отсутствует ключ {e} в ответе {data}")
        await update.message.reply_text(
            "⚠️ Получены некорректные данные от WeatherAPI. Попробуй позже или другой город.",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Неожиданная ошибка при получении погоды: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Произошла неожиданная ошибка: {e}\nПопробуй позже.",
            reply_markup=reply_markup
        )

# -------------------
# Main
# -------------------

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_city)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🌤 Бот (на базе WeatherAPI) запущен...")
    app.run_polling()