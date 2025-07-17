from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base

# Базова директорія
BASE_DIR = Path(__file__).parent.parent

# Шлях до бази даних
DB_PATH = f"sqlite:///{str(BASE_DIR / 'db.sqlite3')}"

print(DB_PATH)

# SQLALCHEMY_DATABASE_URL = "sqlite:///./finance.db"
engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# def init_db():
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

