import os
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler
from flask import Flask, request, jsonify
import json
from threading import Thread
from flask_cors import CORS  # Импорт в начало

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Токен бота (вставь свой из BotFather)
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'твой_токен_здесь')

# Тестовый режим
TEST_MODE = True

# Глобальные переменные
user_data = {}
jobs = {}

# Сохранение данных
def save_data():
    try:
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in user_data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

# Загрузка данных
def load_data():
    global user_data
    try:
        with open('user_data.json', 'r', encoding='utf-8') as f:
            user_data = {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        user_data = {}
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")

# Flask приложение для API
app = Flask(__name__)
CORS(app)  # Включаем CORS для всего приложения

@app.route('/status', methods=['POST'])
@cross_origin()  # Декоратор над функцией
def update_status():
    data = request.json
    user_id = data.get('user_id')
    status = data.get('status')
    if not user_id or status not in ['дома', 'не дома']:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    if user_id not in user_data:
        user_data[user_id] = {'status': 'дома', 'emergency_contact': '', 'left_home_time': None, 'warnings_sent': 0}
    user_data[user_id]['status'] = status
    if status == 'не дома':
        user_data[user_id]['left_home_time'] = datetime.now()
        user_data[user_id]['warnings_sent'] = 0
        if TEST_MODE:
            job_timeout = 60  # 1 минута
        else:
            job_timeout = 24 * 3600  # 24 часа
        try:
            job = application.job_queue.run_once(check_user_status_callback, job_timeout, data=user_id, name=str(user_id))
            jobs[str(user_id)] = job
            logger.info(f"Запущен таймер для {user_id}")
        except Exception as e:
            logger.error(f"Ошибка таймера: {e}")
    save_data()
    return jsonify({'success': True})

@app.route('/contact', methods=['POST'])
@cross_origin()  # Декоратор над функцией
def update_contact():
    data = request.json
    user_id = data.get('user_id')
    contact = data.get('contact')
    if not user_id or not contact.startswith('@'):
        return jsonify({'success': False, 'error': 'Invalid contact'}), 400
    if user_id not in user_data:
        user_data[user_id] = {'status': 'дома', 'emergency_contact': '', 'left_home_time': None, 'warnings_sent': 0}
    user_data[user_id]['emergency_contact'] = contact
    save_data()
    return jsonify({'success': True})

# Таймер для проверки статуса
async def check_user_status_callback(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data
    logger.info(f"Проверка для {user_id} в {datetime.now().strftime('%H:%M:%S')}")
    if user_id not in user_data or user_data[user_id]['status'] != 'не дома':
        return
    data = user_data[user_id]
    if TEST_MODE:
        warning_text = "🤗 Проверка! Прошло 1 минута. Отметь 'Дома' или контакт узнает!"
        emergency_timeout = 30  # 30 секунд
    else:
        warning_text = "🤗 Проверка! Прошло 24 часа. Отметь 'Дома' или контакт узнает!"
        emergency_timeout = 3600  # 1 час
    try:
        await context.bot.send_message(chat_id=user_id, text=warning_text)
        data['warnings_sent'] = 1
        save_data()
        emergency_job = context.job_queue.run_once(send_emergency_alert_callback, emergency_timeout, data=user_id, name=f"{user_id}_emergency")
        jobs[f"{user_id}_emergency"] = emergency_job
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

# Таймер для экстренного сообщения
async def send_emergency_alert_callback(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data
    logger.info(f"Экстренное для {user_id} в {datetime.now().strftime('%H:%M:%S')}")
    if user_id not in user_data or user_data[user_id]['status'] != 'не дома':
        return
    data = user_data[user_id]
    emergency_contact = data['emergency_contact']
    if TEST_MODE:
        message = f"🚨 Тест! {user_id} не отвечает 1.5 мин. Проверь!"
    else:
        message = f"🚨 Экстренно! {user_id} не отвечает 25 часов. Проверь!"
    try:
        await context.bot.send_message(chat_id=emergency_contact, text=message)
        await context.bot.send_message(chat_id=user_id, text="🚨 Контакт уведомлён! Отметь 'Дома'!")
        data['warnings_sent'] = 2
        save_data()
    except Exception as e:
        logger.error(f"Ошибка экстренного: {e}")

# Инициализация бота
application = Application.builder().token(BOT_TOKEN).build()
application.job_queue.start()
application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Добро пожаловать в Mini App! Открой его через меню.")))

# Запуск
def run_bot():
    application.run_polling()

if __name__ == '__main__':
    load_data()
    Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
