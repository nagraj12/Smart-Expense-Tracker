from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "expenses.db"


def create_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, definition: str) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row["name"] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def create_table() -> None:
    conn = create_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL UNIQUE,
            contact_number TEXT,
            address TEXT,
            category_specialization TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT DEFAULT 'units',
            unit_price REAL,
            total_amount REAL NOT NULL,
            paid_amount REAL NOT NULL DEFAULT 0,
            balance_amount REAL NOT NULL DEFAULT 0,
            transaction_date TEXT NOT NULL,
            due_date TEXT,
            notes TEXT,
            category_confidence REAL DEFAULT 0,
            category_source TEXT DEFAULT 'rule-based',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_transaction_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            paid_amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            payment_mode TEXT,
            payment_note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_transaction_id) REFERENCES supplier_transactions (id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL UNIQUE
        )
        """
    )

    for category_name in [
        "Groceries",
        "Dairy",
        "Beverages",
        "Snacks",
        "Household Items",
        "Personal Care",
        "Frozen Foods",
        "Bakery",
        "Other",
    ]:
        cursor.execute(
            "INSERT OR IGNORE INTO categories (category_name) VALUES (?)",
            (category_name,),
        )

    ensure_column(cursor, "supplier_transactions", "notes", "TEXT")
    ensure_column(cursor, "supplier_transactions", "due_date", "TEXT")
    ensure_column(cursor, "supplier_transactions", "category_confidence", "REAL DEFAULT 0")
    ensure_column(cursor, "supplier_transactions", "category_source", "TEXT DEFAULT 'rule-based'")
    ensure_column(cursor, "supplier_transactions", "unit", "TEXT DEFAULT 'units'")
    ensure_column(cursor, "supplier_transactions", "unit_price", "REAL")
    ensure_column(cursor, "payments", "payment_mode", "TEXT")

    conn.commit()
    conn.close()
