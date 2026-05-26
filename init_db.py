"""Initialize the SQLite database from schema.sql.

Run once after install:
    python init_db.py

Re-running is safe (uses CREATE TABLE IF NOT EXISTS). For development,
pass --reset to drop existing tables first (useful after schema changes):
    python init_db.py --reset

If SEED_ADMIN_EMAIL and SEED_ADMIN_PHONE are set in the environment,
also inserts (or skips if already present) an admin user. Admins log in
the same way as everyone else: phone + OTP.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
INSTANCE_DIR = PROJECT_ROOT / "instance"
SCHEMA_FILE = PROJECT_ROOT / "schema.sql"
DB_FILENAME = os.environ.get("DATABASE_PATH", "kaampaao.db")
DB_PATH = INSTANCE_DIR / DB_FILENAME


def main() -> None:
    reset = "--reset" in sys.argv[1:]
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        if reset:
            conn.executescript(
                "DROP TABLE IF EXISTS provider_review_log;"
                "DROP TABLE IF EXISTS provider_documents;"
                "DROP TABLE IF EXISTS provider_profiles;"
                "DROP TABLE IF EXISTS otp_codes;"
                "DROP TABLE IF EXISTS users;"
            )
            print("Dropped existing tables.")
        conn.executescript(schema)
        conn.commit()
        print(f"Schema applied to {DB_PATH}")
        _maybe_seed_admin(conn)
    finally:
        conn.close()


def _maybe_seed_admin(conn: sqlite3.Connection) -> None:
    email = (os.environ.get("SEED_ADMIN_EMAIL") or "").strip().lower()
    phone = (os.environ.get("SEED_ADMIN_PHONE") or "").strip()
    name = (os.environ.get("SEED_ADMIN_NAME") or "Admin").strip()
    if not email or not phone:
        return

    existing = conn.execute(
        "SELECT 1 FROM users WHERE email = ? OR phone = ?", (email, phone)
    ).fetchone()
    if existing:
        print(f"Admin {email} already exists; skipping seed.")
        return

    conn.execute(
        "INSERT INTO users (name, email, phone, role) VALUES (?, ?, ?, 'admin')",
        (name, email, phone),
    )
    conn.commit()
    print(f"Seeded admin user: {email} ({phone})")


if __name__ == "__main__":
    main()
