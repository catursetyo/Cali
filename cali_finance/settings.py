from __future__ import annotations

from datetime import datetime

from .config import TZ
from .db import connect
from .money import parse_amount


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = connect()
    row = conn.execute("SELECT value FROM finance_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> dict:
    allowed = {
        "minimum_reserve",
        "monthly_savings_target",
        "duplicate_window_days",
        "backup_stale_hours",
        "due_soon_days",
    }
    if key not in allowed:
        raise ValueError(f"Setting tidak dikenal: {key}")
    if key in {"minimum_reserve", "monthly_savings_target"}:
        value = str(parse_amount(value, allow_zero=True))
    elif key in {"duplicate_window_days", "backup_stale_hours", "due_soon_days"}:
        parsed = int(value)
        if parsed < 0:
            raise ValueError("Nilai setting tidak boleh negatif.")
        value = str(parsed)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn = connect()
    conn.execute(
        """
        INSERT INTO finance_settings(key,value,updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
        """,
        (key, value, now),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "key": key, "value": value}


def all_settings() -> dict[str, str]:
    conn = connect()
    rows = conn.execute("SELECT key,value FROM finance_settings ORDER BY key").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}
