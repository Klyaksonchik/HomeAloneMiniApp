import os
import logging
import httpx
from datetime import datetime, timezone
from threading import Thread, Timer
from contextlib import contextmanager

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import Conflict

from models import SessionLocal, User, init_db
from telegram_webapp_auth import telegram_user_id_from_init_data

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Конфиг --------------------
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена")

# Тестовые интервалы: сразу/30/30 секунд. В проде можно заменить на часы.
TEST_MODE = True
REMINDER_1_DELAY = 0 if TEST_MODE else 24 * 3600  # Сразу после истечения таймера
REMINDER_2_DELAY = 30 if TEST_MODE else 3600  # 30 секунд после первого напоминания
EMERGENCY_DELAY = 30 if TEST_MODE else 3600  # 30 секунд после второго напоминания

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


def ensure_utc_aware(dt):
    """Преобразует datetime в UTC-aware формат"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fix_user_left_home_time(user):
    """Исправляет left_home_time пользователя, если оно timezone-naive"""
    if user and user.left_home_time and user.left_home_time.tzinfo is None:
        logger.warning("⚠️ Исправление timezone-naive left_home_time для user_id=%s", user.user_id)
        user.left_home_time = user.left_home_time.replace(tzinfo=timezone.utc)
        return True
    return False


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
            db.commit()
            logger.info("✅ Новый пользователь зарегистрирован: user_id=%s, username=%s", user_id, username)
            await update.message.reply_text(
                "✅ Ты зарегистрирован в системе! Запускай приложение по кнопке ниже"
            )
        else:
            # Обновляем данные существующего пользователя
            user.username = username
            user.chat_id = user_id
            db.commit()
            logger.info("✅ Пользователь обновлен: user_id=%s, username=%s", user_id, username)
            await update.message.reply_text(
                "✅ Добро пожаловать обратно! Запускай приложение по кнопке ниже"
            )
        
        # Если у пользователя есть username, проверяем, не является ли он экстренным контактом для других пользователей
        if username:
            # Находим всех пользователей, у которых указан этот username как экстренный контакт
            users_with_this_contact = db.query(User).filter(
                User.emergency_contact_username == username,
                User.emergency_contact_user_id.is_(None)  # Обновляем только тех, у кого еще не установлен ID
            ).all()
            
            if users_with_this_contact:
                updated_count = 0
                for u in users_with_this_contact:
                    u.emergency_contact_user_id = user_id  # Используем user_id как chat_id для отправки сообщений
                    updated_count += 1
                db.commit()
                logger.info("🔗 Обновлен emergency_contact_user_id для %s пользователей, которые указали %s как экстренный контакт", 
                          updated_count, username)


application.add_handler(CommandHandler("start", cmd_start))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для бота"""
    error = context.error
    if isinstance(error, Conflict):
        # Conflict 409 - это нормально при деплое, когда старый экземпляр еще работает
        # Не останавливаем polling, просто логируем - система сама переключится на новый экземпляр
        logger.warning("⚠️ Conflict 409: другой экземпляр бота уже запущен. Это нормально при деплое. Продолжаем работу...")
        return
    logger.exception("Необработанная ошибка: %s", error)


application.add_error_handler(error_handler)


def send_message_async(chat_id: int, text: str) -> None:
    """Отправляет сообщение через Telegram HTTP API (надежнее для threading.Timer)
    
    Явно указывает disable_notification=False для включения звука и вибрации.
    Примечание: окончательное решение о звуке/вибрации принимает пользователь в настройках Telegram.
    """
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        # Явно указываем disable_notification=False для включения уведомлений со звуком
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": False  # Гарантируем, что уведомления включены
        }
        resp = httpx.post(url, json=payload, timeout=10.0)
        if resp.status_code >= 400:
            logger.error("❌ HTTP API sendMessage FAILED: chat_id=%s, status=%s, response=%s", 
                        chat_id, resp.status_code, resp.text[:200])
        else:
            logger.info("✅ Сообщение отправлено: chat_id=%s, text=%s", chat_id, text[:50])
    except httpx.TimeoutException:
        logger.error("⏱️ Timeout при отправке сообщения: chat_id=%s", chat_id)
    except Exception as e:
        logger.exception("❌ HTTP API отправка не удалась: chat_id=%s, error=%s", chat_id, e)


def _reminder1(user_id: int) -> None:
    """Первое напоминание пользователю"""
    logger.info("🔔 _reminder1 сработал для user_id=%s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        logger.info("⏭️ Пропуск _reminder1: пользователь уже дома или не найден (user_id=%s)", user_id)
        return
    send_message_async(user_id, "🤗 Ты в порядке? Отметься, что ты дома. Сдвинь слайдер в положение \"ДОМА\".")
    update_user(user_id, warnings_sent=1)
    t2 = Timer(REMINDER_2_DELAY, _reminder2, args=(user_id,))
    jobs[f"{user_id}:rem2"] = t2
    t2.start()
    logger.info("⏰ Запущен таймер для _reminder2 (user_id=%s, delay=%s сек)", user_id, REMINDER_2_DELAY)


def _reminder2(user_id: int) -> None:
    """Второе напоминание пользователю"""
    logger.info("🔔 _reminder2 сработал для user_id=%s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        logger.info("⏭️ Пропуск _reminder2: пользователь уже дома или не найден (user_id=%s)", user_id)
        return
    send_message_async(user_id, "🤗 Напоминание! Если ты уже дома — отметься. Сдвинь слайдер в положение \"ДОМА\".")
    update_user(user_id, warnings_sent=2)
    t3 = Timer(EMERGENCY_DELAY, _emergency, args=(user_id,))
    jobs[f"{user_id}:emerg"] = t3
    t3.start()
    logger.info("⏰ Запущен таймер для _emergency (user_id=%s, delay=%s сек)", user_id, EMERGENCY_DELAY)


def _emergency(user_id: int) -> None:
    """Экстренное уведомление контакту"""
    logger.info("🚨 _emergency сработал для user_id=%s", user_id)
    user_data = get_user(user_id)
    if not user_data or user_data.get("status") != "не дома":
        logger.info("⏭️ Пропуск _emergency: пользователь уже дома или не найден (user_id=%s)", user_id)
        return

    emergency_contact_user_id = user_data.get("emergency_contact_user_id")
    emergency_contact_username = user_data.get("emergency_contact_username")

    if not emergency_contact_user_id and emergency_contact_username:
        logger.info("🔍 Поиск экстренного контакта по username: %s", emergency_contact_username)
        with get_db_session() as db:
            contact_user = db.query(User).filter(
                User.username == emergency_contact_username,
                User.chat_id.isnot(None)
            ).first()
            if contact_user:
                emergency_contact_user_id = contact_user.chat_id
                update_user(user_id, emergency_contact_user_id=emergency_contact_user_id)
                logger.info("✅ Найден экстренный контакт: emergency_contact_username=%s, contact_user.user_id=%s, contact_user.chat_id=%s", 
                          emergency_contact_username, contact_user.user_id, emergency_contact_user_id)
            else:
                logger.warning("⚠️ Экстренный контакт не найден в БД: emergency_contact_username=%s", emergency_contact_username)

    if not emergency_contact_user_id:
        logger.error("❌ Не удалось найти экстренный контакт для user_id=%s, emergency_contact_username=%s", 
                    user_id, emergency_contact_username)
        send_message_async(user_id, "⚠️ Экстренный контакт ещё не активировал бота или не указан.")
        return

    # Имя для отображения: предпочитаем username, иначе id
    display_name = user_data.get("username") or f"id {user_id}"
    logger.info("📤 Отправка экстренного уведомления: emergency_contact_username=%s, emergency_contact_user_id=%s, пользователь=%s", 
               emergency_contact_username, emergency_contact_user_id, display_name)
    try:
        send_message_async(
            emergency_contact_user_id,
            f"🚨 Твой друг {display_name} не выходит на связь. Проверь, всё ли с ним в порядке. Его питомец дома совсем один!"
        )
        logger.info("✅ Экстренное уведомление успешно отправлено контакту: emergency_contact_user_id=%s", emergency_contact_user_id)
    except Exception as e:
        logger.error("❌ Ошибка Telegram sendMessage при отправке экстренного уведомления: emergency_contact_user_id=%s, error=%s", 
                   emergency_contact_user_id, e)
    
    try:
        send_message_async(user_id, f"🚨 Экстренный контакт {emergency_contact_username} уведомлён! Если ты в порядке — отметься. Сдвинь слайдер в положение \"ДОМА\".")
    except Exception as e:
        logger.error("❌ Ошибка Telegram sendMessage при отправке подтверждения пользователю: user_id=%s, error=%s", user_id, e)


def cancel_all_jobs_for_user(user_id: int) -> None:
    """Отменяет все активные таймеры для пользователя"""
    keys = [f"{user_id}:rem1", f"{user_id}:rem2", f"{user_id}:emerg"]
    cancelled = 0
    for k in keys:
        job = jobs.pop(k, None)
        if job:
            try:
                job.cancel()
                cancelled += 1
            except Exception as e:
                logger.warning("⚠️ Ошибка при отмене таймера %s: %s", k, e)
    if cancelled > 0:
        logger.info("⏹️ Отменено таймеров для user_id=%s: %s", user_id, cancelled)


def schedule_sequence_for_user(user_id: int, timer_seconds: int = None) -> None:
    """Планирует цепочку таймеров для пользователя"""
    user_data = get_user(user_id)
    # Используем таймер пользователя, если не указан явно
    if timer_seconds is None:
        timer_seconds = user_data.get("timer_seconds") if user_data else 3600
    
    logger.info("⏰ Планирование таймеров для user_id=%s: timer_seconds=%s", user_id, timer_seconds)
    # Первый таймер на указанное время
    t1 = Timer(timer_seconds, _reminder1, args=(user_id,))
    jobs[f"{user_id}:rem1"] = t1
    t1.start()
    logger.info("✅ Запущен первый таймер для user_id=%s (через %s сек)", user_id, timer_seconds)


# -------------------- Flask app --------------------
INIT_DATA_HEADER = "X-Telegram-Init-Data"


def _cors_allowed_origins():
    default = [
        "https://web.telegram.org",
        "https://webk.telegram.org",
        "https://telegram.org",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    extra = os.environ.get("EXTRA_CORS_ORIGINS", "").strip()
    if not extra:
        return default
    return default + [x.strip() for x in extra.split(",") if x.strip()]


def _raw_init_data_candidates() -> list[str]:
    """
    Все непустые варианты initData из запроса. Длинные строки идут первыми:
    иногда заголовок обрезают прокси, а query/body содержат полный payload.
    """
    seen: set[str] = set()
    chunks: list[str] = []

    def add(s: str | None) -> None:
        t = (s or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        chunks.append(t)

    add(request.headers.get(INIT_DATA_HEADER))
    add(request.headers.get("X-Telegram-Web-App-Init-Data"))
    auth = (request.headers.get("Authorization") or "").strip()
    if auth[:4].lower() == "tma " and len(auth) > 4:
        add(auth[4:])
    add(request.args.get("init_data"))
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            b = body.get("init_data")
            if isinstance(b, str):
                add(b)
    chunks.sort(key=len, reverse=True)
    return chunks


def get_authenticated_telegram_user_id() -> int | None:
    """user_id только из проверенного initData (не из поля user_id в теле)."""
    for raw in _raw_init_data_candidates():
        uid = telegram_user_id_from_init_data(raw, BOT_TOKEN)
        if uid is not None:
            return uid
    return None


app = Flask(__name__)
CORS(
    app,
    origins=_cors_allowed_origins(),
    supports_credentials=False,
    allow_headers=[
        "Content-Type",
        INIT_DATA_HEADER,
        "X-Telegram-Web-App-Init-Data",
        "Authorization",
    ],
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["180 per minute"],
    storage_uri="memory://",
)


@app.route("/")
def root() -> str:
    return "Backend работает ✅"


@app.route("/status", methods=["POST"])
@cross_origin()
@limiter.limit("45 per minute")
def http_update_status():
    try:
        user_id = get_authenticated_telegram_user_id()
        if user_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "unauthorized",
                        "message": "Откройте мини‑апп из Telegram или обновите страницу.",
                    }
                ),
                401,
            )

        payload = request.json or {}
        status = payload.get("status")
        username = payload.get("username")
        timer_seconds = payload.get("timer_seconds")  # Новый параметр для таймера

        if status not in ("дома", "не дома"):
            return jsonify({"success": False, "error": "Invalid data"}), 400

        with get_db_session() as db:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    status=status,
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
            logger.info("🚶 Пользователь user_id=%s переключился в статус 'не дома'", user_id)
            update_user(
                user_id,
                left_home_time=datetime.now(timezone.utc),
                warnings_sent=0
            )
            cancel_all_jobs_for_user(user_id)
            try:
                schedule_sequence_for_user(user_id, saved_timer_seconds)
            except Exception as e:
                logger.exception("❌ Ошибка планирования таймеров для user_id=%s: %s", user_id, e)
                return jsonify({"success": False, "error": "Timer scheduling failed"}), 500
            logger.info("✅ Запущены таймеры для user_id=%s (таймер: %s сек)", user_id, saved_timer_seconds)
        else:  # статус "дома"
            logger.info("🏠 Пользователь user_id=%s переключился в статус 'дома'", user_id)
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
@limiter.limit("90 per minute")
def http_get_status():
    try:
        user_id = get_authenticated_telegram_user_id()
        if user_id is None:
            return jsonify({"error": "unauthorized"}), 401

        user_data = get_user(user_id)
        status = user_data.get("status") or "дома"
        
        # Вычисляем оставшееся время, если пользователь "не дома"
        time_remaining = None
        elapsed_seconds = None
        left_home_time = None
        
        if status == "не дома":
            with get_db_session() as db:
                user = db.query(User).filter(User.user_id == user_id).first()
                if user and user.left_home_time:
                    # Исправляем timezone-naive, если нужно
                    if fix_user_left_home_time(user):
                        db.commit()
                    
                    left_home_time = user.left_home_time
                    left_time = ensure_utc_aware(user.left_home_time)
                    if left_time:
                        timer_seconds = user.timer_seconds or 3600
                        elapsed_seconds = (datetime.now(timezone.utc) - left_time).total_seconds()
                        time_remaining = max(0, timer_seconds - elapsed_seconds)
                        if time_remaining <= 0:
                            time_remaining = 0
        
        logger.info("GET /status: user_id=%s, status=%s, left_home_time=%s, elapsed_seconds=%s", 
                   user_id, status, left_home_time, elapsed_seconds)
        
        return jsonify({
            "status": status,
            "emergency_contact_set": bool(user_data.get("emergency_contact_username")),
            "timer_seconds": user_data.get("timer_seconds") or 3600,
            "time_remaining": int(time_remaining) if time_remaining is not None else None,
            "elapsed_seconds": int(elapsed_seconds) if elapsed_seconds is not None else None,
        }), 200
    except Exception as e:
        logger.exception("❌ Ошибка GET /status: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/contact", methods=["POST", "GET"])
@cross_origin()
@limiter.limit("60 per minute")
def http_update_contact():
    user_id = get_authenticated_telegram_user_id()
    if user_id is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "unauthorized",
                    "message": "Откройте мини‑апп из Telegram.",
                }
            ),
            401,
        )

    if request.method == "POST":
        payload = request.json or {}
        contact = payload.get("contact")

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
            
            # Сразу пытаемся найти контакт по username и обновить emergency_contact_user_id
            # Это решает проблему, когда контакт уже зарегистрирован, но ID еще не установлен
            contact_user = db.query(User).filter(
                User.username == contact,
                User.chat_id.isnot(None)
            ).first()
            
            if contact_user:
                # Контакт уже зарегистрирован - сразу обновляем ID
                user.emergency_contact_user_id = contact_user.user_id
                logger.info("✅ При сохранении контакта сразу найден emergency_contact_user_id: user_id=%s, contact=%s, contact_user_id=%s", 
                          user_id, contact, contact_user.user_id)
            else:
                # Контакт еще не зарегистрирован - сбрасываем ID, он обновится при /start контакта
                user.emergency_contact_user_id = None
                logger.info("ℹ️ Контакт %s еще не зарегистрирован. ID обновится при /start контакта (user_id=%s)", 
                          contact, user_id)
            
            db.commit()

        return jsonify({"success": True})

    # GET
    user_data = get_user(user_id)
    value = user_data.get("emergency_contact_username") if user_data and user_data.get("emergency_contact_username") else ""
    return jsonify({"emergency_contact": value}), 200


@app.route("/timer", methods=["POST", "GET"])
@cross_origin()
@limiter.limit("60 per minute")
def http_timer():
    """Эндпоинт для работы с таймером"""
    user_id = get_authenticated_telegram_user_id()
    if user_id is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "unauthorized",
                    "message": "Откройте мини‑апп из Telegram.",
                }
            ),
            401,
        )

    if request.method == "POST":
        payload = request.json or {}
        timer_seconds = payload.get("timer_seconds")

        try:
            timer_seconds = int(timer_seconds)
            if timer_seconds < 60:  # Минимум 1 минута
                return jsonify({"success": False, "error": "Timer must be at least 60 seconds"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid timer_seconds"}), 400

        update_user(user_id, timer_seconds=timer_seconds)
        return jsonify({"success": True})

    # GET
    user_data = get_user(user_id)
    return jsonify({"timer_seconds": user_data.get("timer_seconds") if user_data else 3600}), 200


def run_flask() -> None:
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 5000))
    logger.info("Запуск Flask сервера на порту %s", port)
    # Используем development server для совместимости с threading.Timer
    # В production можно использовать gunicorn, но тогда нужно переделать таймеры
    app.run(host="0.0.0.0", port=port, debug=False)


@app.route("/debug", methods=["GET"])
@limiter.limit("10 per minute")
def http_debug():
    secret = os.environ.get("DEBUG_SECRET", "").strip()
    if not secret or request.headers.get("X-Debug-Secret", "").strip() != secret:
        return jsonify({"error": "not found"}), 404
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
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.exception("❌ Ошибка инициализации БД: %s", e)
        raise

    # Проверка переменных окружения
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        raise RuntimeError("BOT_TOKEN не установлен")
    
    port = int(os.environ.get("PORT", 5000))
    logger.info("🚀 Запуск приложения на порту %s", port)
    
    # Поднимаем Flask в фоне, а бота — в главном потоке
    flask_thread = Thread(target=run_flask, daemon=True, name="FlaskThread")
    flask_thread.start()
    logger.info("✅ Flask сервер запущен в фоновом потоке")
    
    # Защита: запускаем polling только если установлена переменная окружения
    run_bot_polling = os.environ.get("RUN_BOT_POLLING", "1").strip().lower() in ("1", "true", "yes")
    
    if not run_bot_polling:
        logger.info("⏸️ RUN_BOT_POLLING не установлен или равен 0. Polling не запускается.")
        # Просто ждем, чтобы процесс не завершился
        try:
            while True:
                import time
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("⏹️ Получен сигнал остановки")
    else:
        logger.info("🤖 Инициализация Telegram бота, polling…")
        # Ошибки Conflict обрабатываются через error_handler
        try:
            application.run_polling(
                drop_pending_updates=True, 
                allowed_updates=Update.ALL_TYPES,
                stop_signals=None  # Не останавливаем при сигналах, чтобы работал в Render
            )
        except Conflict as e:
            # Conflict 409 при запуске - это нормально при деплое, когда старый экземпляр еще работает
            # Просто логируем и завершаем - Render автоматически переключится на новый экземпляр
            logger.warning("⚠️ Conflict 409 при запуске polling: %s. Это нормально при деплое. Завершаем этот экземпляр.", e)
            logger.info("⏹️ Завершение работы из-за конфликта (новый экземпляр должен запуститься)")
        except KeyboardInterrupt:
            logger.info("⏹️ Получен сигнал остановки")
        except Exception as e:
            logger.exception("❌ Критическая ошибка бота: %s", e)
            raise

