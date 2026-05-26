"""OTP issuance, storage, and verification.

Storage: SQLite `otp_codes` table (hashed code, expiry, attempt counter).
Delivery: pluggable. Current providers:
    - "dev"  -> print code to server console and return it to the caller
               (the JSON API surfaces it so the page can show a dev banner).
    - "log"  -> print to server console only; do not return.

Swapping in a real provider (Twilio, MSG91, AWS SNS) is a `send` function
in this file plus an OTP_PROVIDER env value.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5
MIN_REQUEST_INTERVAL = timedelta(seconds=30)  # per phone+purpose
PURPOSES = ("login", "signup_verify")

PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")


# --- Phone helpers ----------------------------------------------------------

def normalize_phone(raw: str | None) -> str | None:
    """Normalize a user-entered phone string to +91XXXXXXXXXX. Returns None if invalid."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        return None
    candidate = "+91" + digits
    return candidate if PHONE_RE.match(candidate) else None


# --- Delivery providers -----------------------------------------------------

@dataclass
class SendResult:
    ok: bool
    dev_code: str | None = None  # populated only by the "dev" provider
    error: str | None = None


def _provider() -> str:
    return (os.environ.get("OTP_PROVIDER") or "dev").lower()


def send_otp(phone: str, code: str, purpose: str) -> SendResult:
    """Deliver an OTP via the configured provider."""
    p = _provider()
    if p == "dev":
        print(f"[OTP dev] phone={phone} purpose={purpose} code={code}", flush=True)
        return SendResult(ok=True, dev_code=code)
    if p == "log":
        print(f"[OTP log] phone={phone} purpose={purpose} code={code}", flush=True)
        return SendResult(ok=True)
    # Real providers go here. For now anything else returns an error so we fail loudly.
    return SendResult(ok=False, error=f"Unknown OTP provider: {p}")


# --- Core issue / verify ----------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _too_soon(conn: sqlite3.Connection, phone: str, purpose: str) -> bool:
    """Throttle: at most one OTP request per phone+purpose per MIN_REQUEST_INTERVAL."""
    row = conn.execute(
        "SELECT created_at FROM otp_codes "
        "WHERE phone = ? AND purpose = ? ORDER BY id DESC LIMIT 1",
        (phone, purpose),
    ).fetchone()
    if not row:
        return False
    last = datetime.fromisoformat(row[0])
    return (_now() - last) < MIN_REQUEST_INTERVAL


def issue(conn: sqlite3.Connection, phone: str, purpose: str) -> tuple[bool, SendResult | str]:
    """Generate, store, and send an OTP. Returns (ok, SendResult-or-error-string)."""
    if purpose not in PURPOSES:
        return False, "invalid purpose"
    if _too_soon(conn, phone, purpose):
        return False, "too_soon"

    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    expires_at = (_now() + OTP_TTL).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO otp_codes (phone, purpose, code_hash, expires_at) VALUES (?, ?, ?, ?)",
        (phone, purpose, generate_password_hash(code), expires_at),
    )
    conn.commit()

    result = send_otp(phone, code, purpose)
    if not result.ok:
        return False, result.error or "send_failed"
    return True, result


def verify(conn: sqlite3.Connection, phone: str, purpose: str, code: str) -> bool:
    """Verify the most recent unconsumed OTP for (phone, purpose). Single-use."""
    if not code or not code.isdigit() or len(code) != OTP_LENGTH:
        return False
    row = conn.execute(
        "SELECT id, code_hash, expires_at, attempts, consumed_at FROM otp_codes "
        "WHERE phone = ? AND purpose = ? AND consumed_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (phone, purpose),
    ).fetchone()
    if not row:
        return False
    otp_id, code_hash, expires_at, attempts, consumed_at = row
    if consumed_at is not None:
        return False
    if attempts >= MAX_ATTEMPTS:
        return False
    if datetime.fromisoformat(expires_at) < _now():
        return False

    # Always count the attempt (whether match or not) to throttle brute force.
    conn.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
    if not check_password_hash(code_hash, code):
        conn.commit()
        return False

    conn.execute(
        "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
        (_now().isoformat(timespec="seconds"), otp_id),
    )
    conn.commit()
    return True


def purge_expired(conn: sqlite3.Connection) -> None:
    """Best-effort cleanup of old rows. Safe to call occasionally."""
    cutoff = (_now() - timedelta(hours=24)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM otp_codes WHERE created_at < ?", (cutoff,))
    conn.commit()
