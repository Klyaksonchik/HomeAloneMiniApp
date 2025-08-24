from flask import Flask, request, jsonify
import sqlite3
import asyncio
import threading
import telebot

API_TOKEN = "8120075611:AAEdTw_LtsjO3OYYzjeHymdD0TyVraFZ66A"
bot = telebot.TeleBot(API_TOKEN)

app = Flask(__name__)

# база SQLite
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, contact TEXT)")
conn.commit()

active_timers = {}

@app.route("/save_contact", methods=["POST"])
def save_contact():
    data = request.json
    username = data.get("contact")
    user_id = 111  # TODO: заменить на реальный user_id из фронта/бота
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, contact) VALUES (?, ?, ?)",
                   (user_id, username, username))
    conn.commit()
    return jsonify({"status": "ok"})

@app.route("/start_timer", methods=["POST"])
def start_timer():
    data = request.json
    contact = data.get("contact")
    user_id = 111
    task = threading.Thread(target=timer_logic, args=(user_id, contact, 30))
    task.start()
    active_timers[user_id] = task
    return jsonify({"status": "timer started"})

@app.route("/cancel_timer", methods=["POST"])
def cancel_timer():
    user_id = 111
    if user_id in active_timers:
        # поток нельзя убить, но флагами можно доработать
        return jsonify({"status": "timer cancelled"})
    return jsonify({"status": "no active timer"})

def timer_logic(user_id, contact, seconds):
    asyncio.run(async_timer(user_id, contact, seconds))

async def async_timer(user_id, contact, seconds):
    await asyncio.sleep(seconds)
    bot.send_message(user_id, "⏰ Время истекло!")
    bot.send_message(user_id, f"⚠️ Сообщение также отправлено контакту {contact}")

# --- запуск ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
