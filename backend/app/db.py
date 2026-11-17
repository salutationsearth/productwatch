from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_columns(table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _add_column_if_missing(table: str, column: str, ddl_type: str) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    cols = _sqlite_columns(table)
    if column in cols:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def migrate_schema() -> None:
    """Lightweight SQLite column adds for evolving hackathon schema."""
    if not settings.database_url.startswith("sqlite"):
        return
    try:
        _sqlite_columns("users")
    except Exception:
        return
    _add_column_if_missing("users", "face_enrolled", "BOOLEAN DEFAULT 0 NOT NULL")
    _add_column_if_missing("users", "face_enrolled_at", "DATETIME")
    _add_column_if_missing("users", "last_marketing_email_at", "DATETIME")
    _add_column_if_missing("user_product_interest", "first_seen_at", "DATETIME")
    _add_column_if_missing("user_product_interest", "last_seen_at", "DATETIME")


def init_db() -> None:
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
