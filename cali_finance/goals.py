from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import TZ
from .db import connect
from .ledger import parse_occurrence, resolve_wallet
from .money import parse_amount, rupiah


def goal_add(
    *,
    name: str,
    target_raw: str | int,
    target_date: str | None = None,
    linked_wallet: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    wallet_id = None
    wallet_name = None
    if linked_wallet:
        wallet = resolve_wallet(conn, linked_wallet)
        wallet_id = wallet["id"]
        wallet_name = wallet["name"]
    target = parse_amount(target_raw)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    try:
        cursor = conn.execute(
            """
            INSERT INTO savings_goals(
                name,target_amount,current_amount,target_date,linked_wallet_id,status,note,created_at
            ) VALUES(?,?,0,?,?, 'active', ?,?)
            """,
            (name.strip(), target, target_date, wallet_id, note, now),
        )
    except Exception as exc:
        conn.close()
        if "UNIQUE" in str(exc):
            raise ValueError(f"Target tabungan {name!r} sudah ada.") from exc
        raise
    conn.commit()
    goal_id = cursor.lastrowid
    conn.close()
    return {
        "ok": True,
        "goal_id": goal_id,
        "name": name.strip(),
        "target": target,
        "target_formatted": rupiah(target),
        "target_date": target_date,
        "linked_wallet": wallet_name,
        "virtual_bucket": True,
    }


def _resolve_goal(conn, goal: str | int):
    if isinstance(goal, int) or str(goal).isdigit():
        row = conn.execute("SELECT * FROM savings_goals WHERE id=?", (int(goal),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM savings_goals WHERE name=? COLLATE NOCASE", (str(goal).strip(),)
        ).fetchone()
    if not row:
        raise ValueError(f"Target tabungan {goal!r} tidak ditemukan.")
    return row


def goal_contribute(
    *,
    goal: str | int,
    amount_raw: str | int,
    wallet_name: str | None = None,
    date_raw: str | None = None,
    note: str | None = None,
    force_over_target: bool = False,
) -> dict[str, Any]:
    conn = connect()
    row = _resolve_goal(conn, goal)
    if row["status"] not in {"active", "paused"}:
        conn.close()
        raise ValueError("Target tabungan tidak aktif.")
    amount = parse_amount(amount_raw)
    if row["current_amount"] + amount > row["target_amount"] and not force_over_target:
        conn.close()
        raise ValueError(
            "Kontribusi melebihi target. Pakai --force-over-target jika memang disengaja."
        )
    wallet_id = None
    wallet_label = None
    if wallet_name:
        wallet = resolve_wallet(conn, wallet_name)
        wallet_id = wallet["id"]
        wallet_label = wallet["name"]
    occurred_at = parse_occurrence(date_raw)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO savings_entries(goal_id,amount,occurred_at,wallet_id,note,created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (row["id"], amount, occurred_at, wallet_id, note, now),
    )
    new_amount = row["current_amount"] + amount
    status = "completed" if new_amount >= row["target_amount"] else "active"
    conn.execute(
        "UPDATE savings_goals SET current_amount=?,status=? WHERE id=?",
        (new_amount, status, row["id"]),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "goal_id": row["id"],
        "name": row["name"],
        "contribution": amount,
        "contribution_formatted": rupiah(amount),
        "current": new_amount,
        "current_formatted": rupiah(new_amount),
        "target": row["target_amount"],
        "target_formatted": rupiah(row["target_amount"]),
        "status": status,
        "wallet_reference": wallet_label,
        "wallet_balance_changed": False,
        "note": "Kontribusi adalah alokasi virtual; saldo dompet tidak berubah.",
    }


def goal_withdraw(
    *,
    goal: str | int,
    amount_raw: str | int,
    date_raw: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    row = _resolve_goal(conn, goal)
    amount = parse_amount(amount_raw)
    if amount > row["current_amount"]:
        conn.close()
        raise ValueError("Penarikan melebihi dana yang sudah dialokasikan.")
    occurred_at = parse_occurrence(date_raw)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO savings_entries(goal_id,amount,occurred_at,note,created_at)
        VALUES(?,?,?,?,?)
        """,
        (row["id"], -amount, occurred_at, note, now),
    )
    new_amount = row["current_amount"] - amount
    conn.execute(
        "UPDATE savings_goals SET current_amount=?,status='active' WHERE id=?",
        (new_amount, row["id"]),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "goal_id": row["id"],
        "name": row["name"],
        "withdrawal": amount,
        "withdrawal_formatted": rupiah(amount),
        "current": new_amount,
        "current_formatted": rupiah(new_amount),
        "wallet_balance_changed": False,
    }


def goals_list(status: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    if status:
        rows = conn.execute(
            """
            SELECT g.*,w.name AS linked_wallet
            FROM savings_goals g LEFT JOIN wallets w ON w.id=g.linked_wallet_id
            WHERE g.status=? ORDER BY g.target_date,g.name
            """,
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT g.*,w.name AS linked_wallet
            FROM savings_goals g LEFT JOIN wallets w ON w.id=g.linked_wallet_id
            ORDER BY CASE g.status WHEN 'active' THEN 0 ELSE 1 END,g.target_date,g.name
            """
        ).fetchall()
    conn.close()
    result = []
    for row in rows:
        progress = row["current_amount"] / row["target_amount"] * 100
        result.append(
            {
                "goal_id": row["id"],
                "name": row["name"],
                "target": row["target_amount"],
                "target_formatted": rupiah(row["target_amount"]),
                "current": row["current_amount"],
                "current_formatted": rupiah(row["current_amount"]),
                "remaining": max(0, row["target_amount"] - row["current_amount"]),
                "remaining_formatted": rupiah(max(0, row["target_amount"] - row["current_amount"])),
                "progress_percent": round(progress, 2),
                "target_date": row["target_date"],
                "linked_wallet": row["linked_wallet"],
                "status": row["status"],
                "virtual_bucket": True,
            }
        )
    return result


def total_allocated_active() -> int:
    conn = connect()
    row = conn.execute(
        "SELECT COALESCE(SUM(current_amount),0) AS total FROM savings_goals WHERE status IN ('active','completed')"
    ).fetchone()
    conn.close()
    return int(row["total"])
