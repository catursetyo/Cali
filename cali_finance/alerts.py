from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from .backup import last_backup
from .budgets import budget_status
from .config import TZ
from .db import connect, db_integrity
from .ledger import all_wallet_balances
from .money import rupiah
from .obligations import obligations_list, recurring_run
from .settings import get_setting


def _is_new(conn, event_key: str, payload: dict[str, Any], mark_sent: bool) -> bool:
    row = conn.execute(
        "SELECT payload_json,last_sent_at FROM notification_events WHERE event_key=?",
        (event_key,),
    ).fetchone()
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    changed = not row or row["last_sent_at"] is None
    if not row:
        conn.execute(
            "INSERT INTO notification_events(event_key,first_seen_at,payload_json) VALUES(?,?,?)",
            (event_key, now, payload_json),
        )
    elif row["payload_json"] != payload_json:
        conn.execute(
            "UPDATE notification_events SET payload_json=? WHERE event_key=?",
            (payload_json, event_key),
        )
    if changed and mark_sent:
        conn.execute(
            "UPDATE notification_events SET last_sent_at=? WHERE event_key=?",
            (now, event_key),
        )
    return changed


def alert_data(*, new_only: bool = False, mark_sent: bool = False) -> dict[str, Any]:
    today = datetime.now(TZ).date()
    due_days = int(get_setting("due_soon_days", "3") or 3)
    stale_hours = int(get_setting("backup_stale_hours", "48") or 48)
    recurring_run(today.isoformat())
    conn = connect()
    alerts: list[dict[str, Any]] = []

    integrity = db_integrity()
    if integrity["integrity"] != "ok" or integrity["foreign_key_errors"]:
        alerts.append({"severity": "critical", "type": "database", "message": "Database integrity check failed.", "details": integrity})

    for wallet in all_wallet_balances(conn):
        if wallet["balance"] < 0:
            alerts.append(
                {
                    "severity": "critical",
                    "type": "negative_balance",
                    "message": f"{wallet['name']} has a negative balance: {wallet['balance_formatted']}",
                    "wallet": wallet["name"],
                    "balance": wallet["balance"],
                }
            )

    for item in obligations_list():
        if item["status"] == "overdue":
            alerts.append(
                {
                    "severity": "critical" if item["remaining_amount"] >= 1_000_000 else "warning",
                    "type": "overdue_obligation",
                    "message": f"#{item['id']} {item['name']} is overdue; {item['remaining_amount_formatted']} remains.",
                    "id": item["id"],
                    "remaining": item["remaining_amount"],
                    "due_date": item["due_date"],
                }
            )
        elif item["status"] in {"open", "partial"} and item["due_date"]:
            due = date.fromisoformat(item["due_date"])
            days = (due - today).days
            if 0 <= days <= due_days:
                alerts.append(
                    {
                        "severity": "warning",
                        "type": "due_soon",
                        "message": f"#{item['id']} {item['name']} is due on {item['due_date']}; {item['remaining_amount_formatted']} remains.",
                        "id": item["id"],
                        "remaining": item["remaining_amount"],
                        "due_date": item["due_date"],
                    }
                )

    for budget in budget_status():
        if budget["threshold"]:
            severity = "critical" if budget["threshold"] >= 100 else "warning"
            alerts.append(
                {
                    "severity": severity,
                    "type": "budget",
                    "message": f"Budget {budget['category']} is at {budget['usage_percent_formatted']} ({budget['spent_formatted']} / {budget['limit_formatted']}).",
                    "budget_id": budget["budget_id"],
                    "threshold": budget["threshold"],
                    "spent": budget["spent"],
                }
            )

    backup = last_backup()
    if not backup:
        alerts.append({"severity": "warning", "type": "backup", "message": "No finance database backup exists yet."})
    else:
        created = datetime.fromisoformat(backup["created_at"])
        age_hours = (datetime.now(TZ) - created.astimezone(TZ)).total_seconds() / 3600
        if age_hours > stale_hours:
            alerts.append(
                {
                    "severity": "warning",
                    "type": "backup",
                    "message": f"The latest backup is {age_hours:.0f} hours old.",
                    "age_hours": round(age_hours, 1),
                    "path": backup["path"],
                }
            )

    pending = conn.execute(
        "SELECT COUNT(*) AS count FROM import_rows WHERE status IN ('unresolved','error','duplicate')"
    ).fetchone()["count"]
    if pending:
        alerts.append(
            {
                "severity": "info",
                "type": "pending_import",
                "message": f"{pending} CSV import rows still need review.",
                "count": pending,
            }
        )

    filtered = []
    for alert in alerts:
        identity = {
            key: alert.get(key)
            for key in ("type", "id", "budget_id", "threshold", "wallet", "due_date")
            if alert.get(key) is not None
        }
        event_key = json.dumps(identity, sort_keys=True, ensure_ascii=True)
        is_new = _is_new(conn, event_key, alert, mark_sent)
        if not new_only or is_new:
            filtered.append(alert)
    conn.commit()
    conn.close()
    return {"ok": True, "alert_count": len(filtered), "alerts": filtered}


def alert_text(data: dict[str, Any]) -> str:
    if not data["alerts"]:
        return ""
    critical = [a for a in data["alerts"] if a["severity"] == "critical"]
    warning = [a for a in data["alerts"] if a["severity"] == "warning"]
    info = [a for a in data["alerts"] if a["severity"] == "info"]
    lines = []
    if critical:
        lines.append("Financial issues need attention now:")
        lines.extend(f"- {item['message']}" for item in critical)
    if warning:
        if lines:
            lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {item['message']}" for item in warning)
    if info:
        if lines:
            lines.append("")
        lines.append("Notes:")
        lines.extend(f"- {item['message']}" for item in info)
    return "\n".join(lines)
