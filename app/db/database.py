import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check your .env file."
    )

# Temporary debugging: shows only the DB URL without the password.
safe_url = DATABASE_URL
if "@" in safe_url and "://" in safe_url:
    prefix, suffix = safe_url.split("@", 1)
    if ":" in prefix:
        prefix = prefix.rsplit(":", 1)[0] + ":****"
    safe_url = prefix + "@" + suffix

print("Database URL:", safe_url)

engine = create_engine(
    DATABASE_URL,
    echo=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()