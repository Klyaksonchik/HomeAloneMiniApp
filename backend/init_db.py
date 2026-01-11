"""
Скрипт для инициализации базы данных.
Запускать один раз при первом деплое или при необходимости пересоздать таблицы.
"""
import os
import logging
from models import init_db, engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("✅ База данных успешно инициализирована!")
    except Exception as e:
        logger.exception("❌ Ошибка инициализации базы данных: %s", e)
        raise

