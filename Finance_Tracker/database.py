"""Database setup helpers for Student Finance Manager."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


# Keep the database file beside app.py, even if the app is started elsewhere.
PROJECT_FOLDER = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_FOLDER / "finance.db"
SCHEMA_PATH = PROJECT_FOLDER / "schema.sql"


@contextmanager
def get_connection():
    """Open a database connection and always close it after use."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create all tables if they do not already exist."""
    with get_connection() as connection:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
