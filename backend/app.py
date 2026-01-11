import os
import logging
import httpx
from datetime import datetime, timezone
from threading import Thread, Timer
from contextlib import contextmanager

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import Conflict

from models import SessionLocal, User, init_db

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Конфиг --------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена")

# Тестовые интервалы: 30/30/30 секунд. В проде можно заменить на часы.
TEST_MODE = True
REMINDER_1_DELAY = 30 if TEST_MODE else 24 * 3600
REMINDER_2_DELAY = 30 if TEST_MODE else 3600
EMERGENCY_DELAY = 30 if TEST_MODE else 3600

# Ключи: f"{user_id}:rem1", f"{user_id}:rem2", f"{user_id}:emerg"
jobs = {}


@contextmanager
def get_db_session():
    """Контекстный менеджер для работы с БД"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_user(user_id: int):
    """Получить пользователя из БД и вернуть словарь с данными"""
    with get_db_session() as db:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(
                user_id=user_id,
                status="дома",
                warnings_sent=0,
                timer_seconds=3600,  # По умолчанию 1 час
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        # Возвращаем словарь, чтобы избежать detached instance
        return {
            "user_id": user.user_id,
            "status": user.status,
            "username": user.username,
            "chat_id": user.chat_id,
            "emergency_contact_username": user.emergency_contact_username,
            "emergency_contact_user_id": user.emergency_contact_user_id,
            "timer_seconds": user.timer_seconds,
            "warnings_sent": user.warnings_sent,
        }


def update_user(user_id: int, **kwargs):
    """Обновить данные пользователя"""
    with get_db_session() as db:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(user_id=user_id, **kwargs)
            db.add(user)
        else:
            for key, value in kwargs.items():
                setattr(user, key, value)
            user.updated_at = datetime.now(timezone.utc)
        db.commit()
        return user


# -------------------- Telegram bot --------------------
application: Application = Application.builder().token(BOT_TOKEN).build()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = (
        f"@{update.effective_user.username}"
        if getattr(update.effective_user, "username", None)
        else None
    )

    with get_db_session() as db:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                chat_id=user_id,
                status="дома",
                warnings_sent=0,
                timer_seconds=3600,
            )
            db.add(user)
        else:
            user.username = username
            user.chat_id = user_id
        db.commit()

    await update.message.reply_text(
        "✅ Ты зарегистрирован в системе! Запускай приложение по кнопке ниже"
    )


application.add_handler(CommandHandler("start", cmd_start))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для бота"""
    error = context.error
    if isinstance(error, Conflict):
        logger.warning("Конфликт: другой экземпляр бота уже запущен. Ожидание...")
        # Бот автоматически переподключится
        return
    logger.exception("Необработанная ошибка: %s", error)


application.add_error_handler(error_handler)


def send_message_async(chat_id: int, text: str) -> None:
    """Пытаемся отправить через PTB; при неудаче — через Telegram HTTP API."""
    # 1) Попытка через PTB (event loop)
    try:
        application.create_task(application.bot.send_message(chat_id=chat_id, text=text))
        logger.info("PTB send_message запланирован: chat_id=%s", chat_id)
        return
    except Exception as e:
        logger.warning("PTB create_task не удался, fallback к HTTP API: %s", e)

    # 2) Резерв: прямой HTTP вызов
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10.0)
        if resp.status_code >= 400:
            logger.error("HTTP API sendMessage %s: %s", resp.status_code, resp.text)
        else:
            logger.info("HTTP API sendMessage OK: chat_id=%s", chat_id)
    except Exception as e:
        logger.exception("HTTP API отправка не удалась: %s", e)


def _reminder1(user_id: int) -> None:
    logger.info("_reminder1 fired for %s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        return
    send_message_async(user_id, "🤗 Ты в порядке? Отметься, что ты дома.")
    update_user(user_id, warnings_sent=1)
    t2 = Timer(REMINDER_2_DELAY, _reminder2, args=(user_id,))
    jobs[f"{user_id}:rem2"] = t2
    t2.start()


def _reminder2(user_id: int) -> None:
    logger.info("_reminder2 fired for %s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        return
    send_message_async(user_id, "🤗 Напоминание! Если ты уже дома — отметься.")
    update_user(user_id, warnings_sent=2)
    t3 = Timer(EMERGENCY_DELAY, _emergency, args=(user_id,))
    jobs[f"{user_id}:emerg"] = t3
    t3.start()


def _emergency(user_id: int) -> None:
    logger.info("_emergency fired for %s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        return

    emergency_contact_user_id = user_data.get("emergency_contact_user_id")
    emergency_contact_username = user_data.get("emergency_contact_username")

    if not emergency_contact_user_id and emergency_contact_username:
        with get_db_session() as db:
            contact_user = db.query(User).filter(
                User.username == emergency_contact_username,
                User.chat_id.isnot(None)
            ).first()
            if contact_user:
                emergency_contact_user_id = contact_user.chat_id
                update_user(user_id, emergency_contact_user_id=emergency_contact_user_id)

    if not emergency_contact_user_id:
        send_message_async(user_id, "⚠️ Экстренный контакт ещё не активировал бота или не указан.")
        return

    # Имя для отображения: предпочитаем username, иначе id
    display_name = user_data.get("username") or f"id {user_id}"
    send_message_async(
        emergency_contact_user_id,
        f"🚨 Твой друг {display_name} не выходит на связь. Проверь, всё ли с ним в порядке."
    )
    send_message_async(user_id, "🚨 Экстренный контакт уведомлён! Если ты в порядке — отметься.")


def cancel_all_jobs_for_user(user_id: int) -> None:
    keys = [f"{user_id}:rem1", f"{user_id}:rem2", f"{user_id}:emerg"]
    for k in keys:
        job = jobs.pop(k, None)
        if job:
            try:
                job.cancel()
            except Exception:
                pass


def schedule_sequence_for_user(user_id: int, timer_seconds: int = None) -> None:
    """Планирует цепочку таймеров для пользователя"""
    user_data = get_user(user_id)
    # Используем таймер пользователя, если не указан явно
    if timer_seconds is None:
        timer_seconds = user_data.get("timer_seconds") if user_data else 3600
    
    # Первый таймер на указанное время
    t1 = Timer(timer_seconds, _reminder1, args=(user_id,))
    jobs[f"{user_id}:rem1"] = t1
    t1.start()


# -------------------- Flask app --------------------
app = Flask(__name__)
CORS(app)


@app.route("/")
def root() -> str:
    return "Backend работает ✅"


@app.route("/status", methods=["POST"])
@cross_origin()
def http_update_status():
    try:
        payload = request.json or {}
        user_id = payload.get("user_id")
        status = payload.get("status")
        username = payload.get("username")
        timer_seconds = payload.get("timer_seconds")  # Новый параметр для таймера

        if user_id is None or status not in ("дома", "не дома"):
            return jsonify({"success": False, "error": "Invalid data"}), 400

        try:
            user_id = int(user_id)
        except Exception:
            return jsonify({"success": False, "error": "Invalid user_id"}), 400

        with get_db_session() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    status="дома",
                    username=username,
                    chat_id=user_id,
                    timer_seconds=timer_seconds if timer_seconds else 3600,
                )
                db.add(user)
            else:
                user.status = status
                if not user.chat_id:
                    user.chat_id = user_id
                if username is not None:
                    user.username = username
                if timer_seconds is not None:
                    user.timer_seconds = timer_seconds
            
            # Проверяем экстренный контакт ДО выхода из контекста
            if status == "не дома":
                # Нельзя уходить из дома без указанного экстренного контакта
                if not user.emergency_contact_username:
                    return jsonify({"success": False, "error": "contact_required"}), 400
            
            db.commit()
            # Сохраняем timer_seconds для использования после выхода из контекста
            saved_timer_seconds = user.timer_seconds

        if status == "не дома":
            update_user(
                user_id,
                left_home_time=datetime.now(timezone.utc),
                warnings_sent=0
            )
            cancel_all_jobs_for_user(user_id)
            try:
                schedule_sequence_for_user(user_id, saved_timer_seconds)
            except Exception as e:
                logger.exception("Ошибка планирования таймеров для %s: %s", user_id, e)
                return jsonify({"success": False, "error": "Timer scheduling failed"}), 500
            logger.info("Запущены таймеры для %s (таймер: %s сек)", user_id, saved_timer_seconds)
        else:  # статус "дома"
            cancel_all_jobs_for_user(user_id)
            update_user(
                user_id,
                left_home_time=None,
                warnings_sent=0
            )

        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Ошибка /status: %s", e)
        return jsonify({"success": False, "error": "Internal Server Error"}), 500


@app.route("/status", methods=["GET"])
@cross_origin()
def http_get_status():
    try:
        user_id = request.args.get("user_id")
        if user_id is None:
            return jsonify({"status": "unknown", "emergency_contact_set": False, "timer_seconds": 3600}), 200
        user_id = int(user_id)
        user_data = get_user(user_id)
        return jsonify({
            "status": user_data.get("status") or "дома",
            "emergency_contact_set": bool(user_data.get("emergency_contact_username")),
            "timer_seconds": user_data.get("timer_seconds") or 3600,
        }), 200
    except Exception as e:
        logger.exception("Ошибка GET /status: %s", e)
        return jsonify({"status": "дома", "emergency_contact_set": False, "timer_seconds": 3600}), 200


@app.route("/contact", methods=["POST", "GET"])
@cross_origin()
def http_update_contact():
    if request.method == "POST":
        payload = request.json or {}
        user_id = payload.get("user_id")
        contact = payload.get("contact")

        try:
            user_id = int(user_id)
        except Exception:
            return jsonify({"success": False, "error": "Invalid user_id"}), 400

        if not isinstance(contact, str):
            return jsonify({"success": False, "error": "Invalid contact"}), 400
        contact = contact.strip()
        if contact and not contact.startswith("@"):
            contact = "@" + contact
        if not contact or contact == "@":
            return jsonify({"success": False, "error": "Invalid contact"}), 400

        with get_db_session() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    status="дома",
                    timer_seconds=3600,
                )
                db.add(user)
            user.emergency_contact_username = contact
            # Сбросить известный ID, он будет резолвиться по username
            user.emergency_contact_user_id = None
            db.commit()

        return jsonify({"success": True})

    # GET
    user_id = request.args.get("user_id")
    try:
        user_id = int(user_id)
    except Exception:
        return jsonify({"emergency_contact": ""}), 200

    user_data = get_user(user_id)
    value = user_data.get("emergency_contact_username") if user_data and user_data.get("emergency_contact_username") else ""
    return jsonify({"emergency_contact": value}), 200


@app.route("/timer", methods=["POST", "GET"])
@cross_origin()
def http_timer():
    """Эндпоинт для работы с таймером"""
    if request.method == "POST":
        payload = request.json or {}
        user_id = payload.get("user_id")
        timer_seconds = payload.get("timer_seconds")

        try:
            user_id = int(user_id)
            timer_seconds = int(timer_seconds)
            if timer_seconds < 60:  # Минимум 1 минута
                return jsonify({"success": False, "error": "Timer must be at least 60 seconds"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid timer_seconds"}), 400

        update_user(user_id, timer_seconds=timer_seconds)
        return jsonify({"success": True})

    # GET
    user_id = request.args.get("user_id")
    try:
        user_id = int(user_id)
    except Exception:
        return jsonify({"timer_seconds": 3600}), 200

    user_data = get_user(user_id)
    return jsonify({"timer_seconds": user_data.get("timer_seconds") if user_data else 3600}), 200


def run_flask() -> None:
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


@app.route("/debug", methods=["GET"])
def http_debug():
    try:
        with get_db_session() as db:
            users = db.query(User).all()
            snapshot = {}
            for user in users:
                snapshot[str(user.user_id)] = user.to_dict()
        return jsonify({"user_data": snapshot, "jobs_keys": list(jobs.keys())})
    except Exception as e:
        logger.exception("Ошибка /debug: %s", e)
        return jsonify({"error": "debug failed"}), 500


if __name__ == "__main__":
    # Инициализация БД при первом запуске
    try:
        init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.exception("Ошибка инициализации БД: %s", e)

    # Поднимаем Flask в фоне, а бота — в главном потоке
    Thread(target=run_flask, daemon=True).start()
    logger.info("Инициализация бота, polling…")
    # Ошибки Conflict обрабатываются через error_handler
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

