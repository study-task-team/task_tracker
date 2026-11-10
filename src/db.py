from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./study_tracker.db"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./study_tracker.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Включаем WAL-режим для SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()