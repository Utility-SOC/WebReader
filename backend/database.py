from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Ensure data directory exists.
# WEBREADER_DATA_DIR (set by the desktop app) points at a user-writable
# location; the default keeps data next to the source for dev/server runs.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_ROOT = os.getenv("WEBREADER_DATA_DIR")
DATA_DIR = os.path.join(_DATA_ROOT, "data") if _DATA_ROOT else os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'webreader.db')}"

# connect_args={"check_same_thread": False} is needed for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
