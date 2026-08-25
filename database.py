"""Database setup helpers for Student Finance Manager."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


PROJECT_FOLDER = Path(__file__).resolve().parent


def get_database_path() -> Path:
    """Determine database path, automatically using /tmp on serverless environments like Vercel."""
    if "DATABASE_PATH" in os.environ:
        return Path(os.environ["DATABASE_PATH"])
    # Detect serverless environment (Vercel, AWS Lambda, etc.) where project root is read-only
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/finance.db")
    return PROJECT_FOLDER / "finance.db"


DATABASE_PATH = get_database_path()
SCHEMA_PATH = PROJECT_FOLDER / "schema.sql"


@contextmanager
def get_connection():
    """Open a database connection and always close it after use."""
    # Ensure parent directory exists (especially for /tmp on cloud platforms)
    if not DATABASE_PATH.parent.exists():
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create or migrate all tables to the multi-user schema."""
    with get_connection() as connection:
        # Check if transactions table exists and lacks user_id
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        )
        table_exists = cursor.fetchone()
        if table_exists:
            columns = [
                col["name"]
                for col in connection.execute("PRAGMA table_info(transactions)").fetchall()
            ]
            if "user_id" not in columns:
                # Need to migrate schema to multi-user
                # Drop old single-user tables without foreign keys
                for table in [
                    "transactions",
                    "budgets",
                    "savings_goals",
                    "recurring_transactions",
                    "debts",
                    "settings",
                ]:
                    connection.execute(f"DROP TABLE IF EXISTS {table}")
                connection.execute("DROP INDEX IF EXISTS idx_budgets_month_category")

        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
