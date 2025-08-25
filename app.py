import os
import json
import logging
import asyncio
import httpx
from datetime import datetime
from threading import Thread, Lock, Timer

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


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


# -------------------- Персистентность --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "user_data.json")

# user_id -> {
#   "status": "дома" | "не дома",
#   "username": "@name" | None,
#   "chat_id": int | None,
#   "emergency_contact_username": "@name" | "",
#   "emergency_contact_user_id": int | None,
#   "left_home_time": datetime | None,
#   "warnings_sent": 0|1|2
# }
user_data = {}

# Ключи: f"{user_id}:rem1", f"{user_id}:rem2", f"{user_id}:emerg"
jobs = {}

data_lock = Lock()


def _serialize_user(record: dict) -> dict:
    copy = dict(record)
    if copy.get("left_home_time") and isinstance(copy["left_home_time"], datetime):
        copy["left_home_time"] = copy["left_home_time"].isoformat()
    return copy


def _deserialize_user(record: dict) -> dict:
    copy = dict(record)
    if copy.get("left_home_time") and isinstance(copy["left_home_time"], str):
        copy["left_home_time"] = datetime.fromisoformat(copy["left_home_time"])
    return copy


def save_data() -> None:
    try:
        with data_lock:
            to_save = {str(uid): _serialize_user(rec) for uid, rec in user_data.items()}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("Ошибка сохранения user_data: %s", e)


def load_data() -> None:
    global user_data
    try:
        if not os.path.exists(DATA_FILE):
            user_data = {}
            return
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        with data_lock:
            user_data = {int(uid): _deserialize_user(rec) for uid, rec in raw.items()}
    except Exception as e:
        logger.exception("Ошибка загрузки user_data: %s", e)
        user_data = {}


# -------------------- Telegram bot --------------------
application: Application = Application.builder().token(BOT_TOKEN).build()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = (
        f"@{update.effective_user.username}"
        if getattr(update.effective_user, "username", None)
        else None
    )

    with data_lock:
        record = user_data.get(user_id, {
            "status": "дома",
            "username": username,
            "chat_id": user_id,
            "emergency_contact_username": "",
            "emergency_contact_user_id": None,
            "left_home_time": None,
            "warnings_sent": 0,
        })
        record["username"] = username
        record["chat_id"] = user_id
        user_data[user_id] = record

    save_data()
    await update.message.reply_text(
        "✅ Ты зарегистрирован в системе! Фронтенд сможет тебя найти."
    )


application.add_handler(CommandHandler("start", cmd_start))


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
    with data_lock:
        rec = user_data.get(user_id)
    if not rec or rec.get("status") != "не дома":
        return
    send_message_async(user_id, "🤗 Ты в порядке? Отметься, что ты дома.")
    with data_lock:
        if user_id in user_data:
            user_data[user_id]["warnings_sent"] = 1
    save_data()
    t2 = Timer(REMINDER_2_DELAY, _reminder2, args=(user_id,))
    with data_lock:
        jobs[f"{user_id}:rem2"] = t2
    t2.start()


def _reminder2(user_id: int) -> None:
    logger.info("_reminder2 fired for %s", user_id)
    with data_lock:
        rec = user_data.get(user_id)
    if not rec or rec.get("status") != "не дома":
        return
    send_message_async(user_id, "🤗 Напоминание! Если ты уже дома — отметься.")
    with data_lock:
        if user_id in user_data:
            user_data[user_id]["warnings_sent"] = 2
    save_data()
    t3 = Timer(EMERGENCY_DELAY, _emergency, args=(user_id,))
    with data_lock:
        jobs[f"{user_id}:emerg"] = t3
    t3.start()


def _emergency(user_id: int) -> None:
    logger.info("_emergency fired for %s", user_id)
    with data_lock:
        rec = user_data.get(user_id)
    if not rec or rec.get("status") != "не дома":
        return

    emergency_contact_user_id = rec.get("emergency_contact_user_id")
    emergency_contact_username = rec.get("emergency_contact_username")

    if not emergency_contact_user_id and emergency_contact_username:
        with data_lock:
            for uid, r in user_data.items():
                if r.get("username") == emergency_contact_username and r.get("chat_id"):
                    emergency_contact_user_id = r.get("chat_id")
                    user_data[user_id]["emergency_contact_user_id"] = emergency_contact_user_id
                    break
        save_data()

    if not emergency_contact_user_id:
        send_message_async(user_id, "⚠️ Экстренный контакт ещё не активировал бота или не указан.")
        return

    send_message_async(emergency_contact_user_id, f"🚨 Твой друг {user_id} не выходит на связь. Проверь, всё ли с ним в порядке.")
    send_message_async(user_id, "🚨 Экстренный контакт уведомлён! Если ты в порядке — отметься.")


def cancel_all_jobs_for_user(user_id: int) -> None:
    keys = [f"{user_id}:rem1", f"{user_id}:rem2", f"{user_id}:emerg"]
    with data_lock:
        for k in keys:
            job = jobs.pop(k, None)
            if job:
                try:
                    job.cancel()
                except Exception:
                    pass


def schedule_sequence_for_user(user_id: int) -> None:
    # Первый таймер на REMINDER_1_DELAY через threading.Timer
    t1 = Timer(REMINDER_1_DELAY, _reminder1, args=(user_id,))
    with data_lock:
        jobs[f"{user_id}:rem1"] = t1
    t1.start()


def schedule_sequence_for_user_safe(user_id: int, attempt: int = 1, max_attempts: int = 10) -> None:
    """Планирует цепочку таймеров с повторными попытками,
    если job_queue ещё не готова после старта приложения."""
    try:
        schedule_sequence_for_user(user_id)
        logger.info("Таймеры запущены для %s", user_id)
    except Exception as e:
        if attempt < max_attempts:
            delay = min(2 * attempt, 10)
            logger.warning(
                "JobQueue не готова (попытка %s/%s). Повтор через %sс. Ошибка: %s",
                attempt,
                max_attempts,
                delay,
                e,
            )
            Timer(delay, schedule_sequence_for_user_safe, args=(user_id, attempt + 1, max_attempts)).start()
        else:
            logger.exception("Не удалось запланировать таймеры для %s после %s попыток: %s", user_id, attempt, e)


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

        if user_id is None or status not in ("дома", "не дома"):
            return jsonify({"success": False, "error": "Invalid data"}), 400

        try:
            user_id = int(user_id)
        except Exception:
            return jsonify({"success": False, "error": "Invalid user_id"}), 400

        with data_lock:
            rec = user_data.get(user_id)
            if not rec:
                rec = {
                    "status": "дома",
                    "username": None,
                    "chat_id": None,
                    "emergency_contact_username": "",
                    "emergency_contact_user_id": None,
                    "left_home_time": None,
                    "warnings_sent": 0,
                }
                user_data[user_id] = rec

            rec["status"] = status
            # Проставим chat_id и username, если не были сохранены
            if not rec.get("chat_id"):
                rec["chat_id"] = user_id
            if username is not None:
                rec["username"] = username

        if status == "не дома":
            with data_lock:
                user_data[user_id]["left_home_time"] = datetime.now()
                user_data[user_id]["warnings_sent"] = 0
            cancel_all_jobs_for_user(user_id)
            try:
                schedule_sequence_for_user(user_id)
            except Exception as e:
                logger.exception("Ошибка планирования таймеров для %s: %s", user_id, e)
                return jsonify({"success": False, "error": "Timer scheduling failed"}), 500
            logger.info("Запущены таймеры для %s", user_id)
        else:  # статус "дома"
            cancel_all_jobs_for_user(user_id)
            with data_lock:
                user_data[user_id]["left_home_time"] = None
                user_data[user_id]["warnings_sent"] = 0

        save_data()
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Ошибка /status: %s", e)
        return jsonify({"success": False, "error": "Internal Server Error"}), 500


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

        if not isinstance(contact, str) or not contact.startswith("@"):
            return jsonify({"success": False, "error": "Invalid contact"}), 400

        with data_lock:
            rec = user_data.get(user_id)
            if not rec:
                rec = {
                    "status": "дома",
                    "username": None,
                    "chat_id": None,
                    "emergency_contact_username": "",
                    "emergency_contact_user_id": None,
                    "left_home_time": None,
                    "warnings_sent": 0,
                }
                user_data[user_id] = rec

            rec["emergency_contact_username"] = contact
            # Сбросить известный ID, он будет резолвиться по username
            rec["emergency_contact_user_id"] = None

        save_data()
        return jsonify({"success": True})

    # GET
    user_id = request.args.get("user_id")
    try:
        user_id = int(user_id)
    except Exception:
        return jsonify({"emergency_contact": ""}), 200

    with data_lock:
        rec = user_data.get(user_id)
        value = rec.get("emergency_contact_username") if rec else ""
    return jsonify({"emergency_contact": value}), 200


def run_flask() -> None:
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


@app.route("/debug", methods=["GET"])  # только для отладки
def http_debug():
    try:
        with data_lock:
            snapshot = {}
            for uid, rec in user_data.items():
                safe = dict(rec)
                if isinstance(safe.get("left_home_time"), datetime):
                    safe["left_home_time"] = safe["left_home_time"].isoformat()
                snapshot[str(uid)] = safe
        return jsonify({"user_data": snapshot, "jobs_keys": list(jobs.keys())})
    except Exception as e:
        logger.exception("Ошибка /debug: %s", e)
        return jsonify({"error": "debug failed"}), 500


if __name__ == "__main__":
    load_data()
    # Поднимаем Flask в фоне, а бота — в главном потоке (чтобы не было проблем с event loop)
    Thread(target=run_flask, daemon=True).start()
    logger.info("Инициализация бота, polling…")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


