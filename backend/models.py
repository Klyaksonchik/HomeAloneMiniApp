from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=True)
    chat_id = Column(Integer, nullable=True)
    status = Column(String(20), default="дома")  # "дома" или "не дома"
    emergency_contact_username = Column(String(255), nullable=True)
    emergency_contact_user_id = Column(Integer, nullable=True)
    left_home_time = Column(DateTime, nullable=True)
    warnings_sent = Column(Integer, default=0)
    timer_seconds = Column(Integer, default=3600)  # Таймер в секундах (по умолчанию 1 час)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "chat_id": self.chat_id,
            "status": self.status,
            "emergency_contact_username": self.emergency_contact_username,
            "emergency_contact_user_id": self.emergency_contact_user_id,
            "left_home_time": self.left_home_time.isoformat() if self.left_home_time else None,
            "warnings_sent": self.warnings_sent,
            "timer_seconds": self.timer_seconds,
        }


# Настройка подключения к БД
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Переменная окружения DATABASE_URL не установлена")

# Для PostgreSQL на Render может потребоваться замена postgres:// на postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def init_db():
    """Создает все таблицы в БД"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Получить сессию БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

