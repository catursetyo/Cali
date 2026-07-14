from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from .config import TZ
from .db import connect
from .ledger import resolve_category
from .money import parse_amount, percent, rupiah


def month_bounds(anchor: date) -> tuple[date, date]:
    start = anchor.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def week_bounds(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=7)


def period_bounds(period_type: str, anchor: date) -> tuple[date, date]:
    if period_type == "month":
        return month_bounds(anchor)
    if period_type == "week":
        return week_bounds(anchor)
    raise ValueError("Budget period must be month or week.")


def budget_set(
    *,
    limit_raw: str | int,
    category_name: str | None = None,
    period_type: str = "month",
    start_date: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    category_id = None
    category_label = "All categories"
    if category_name:
        category = resolve_category(conn, category_name, "expense")
        category_id = category["id"]
        category_label = category["name"]
    anchor = date.fromisoformat(start_date) if start_date else datetime.now(TZ).date()
    start, end = period_bounds(period_type, anchor)
    limit_amount = parse_amount(limit_raw)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    row = conn.execute(
        """
        SELECT id FROM budgets
        WHERE COALESCE(category_id,0)=COALESCE(?,0)
          AND period_type=? AND start_date=?
        """,
        (category_id, period_type, start.isoformat()),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE budgets SET limit_amount=?,end_date=?,active=1 WHERE id=?",
            (limit_amount, end.isoformat(), row["id"]),
        )
        budget_id = row["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO budgets(
                category_id,period_type,limit_amount,start_date,end_date,active,created_at
            ) VALUES(?,?,?,?,?,1,?)
            """,
            (category_id, period_type, limit_amount, start.isoformat(), end.isoformat(), now),
        )
        budget_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "budget_id": budget_id,
        "category": category_label,
        "period_type": period_type,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "limit": limit_amount,
        "limit_formatted": rupiah(limit_amount),
    }


def _spent_for_budget(conn, budget) -> int:
    start_dt = datetime.combine(date.fromisoformat(budget["start_date"]), time.min, TZ)
    end_dt = datetime.combine(date.fromisoformat(budget["end_date"]), time.min, TZ)
    if budget["category_id"] is None:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM transactions
            WHERE status='active' AND type='expense'
              AND occurred_at>=? AND occurred_at<?
            """,
            (start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM transactions
            WHERE status='active' AND type='expense' AND category_id=?
              AND occurred_at>=? AND occurred_at<?
            """,
            (
                budget["category_id"],
                start_dt.isoformat(timespec="seconds"),
                end_dt.isoformat(timespec="seconds"),
            ),
        ).fetchone()
    return int(row["total"])


def budget_status(
    *,
    anchor_date: str | None = None,
    period_type: str | None = None,
    category_name: str | None = None,
) -> list[dict[str, Any]]:
    anchor = date.fromisoformat(anchor_date) if anchor_date else datetime.now(TZ).date()
    conn = connect()
    conditions = ["b.active=1", "b.start_date<=?", "b.end_date>?"]
    params: list[Any] = [anchor.isoformat(), anchor.isoformat()]
    if period_type:
        conditions.append("b.period_type=?")
        params.append(period_type)
    if category_name:
        category = resolve_category(conn, category_name, "expense")
        conditions.append("b.category_id=?")
        params.append(category["id"])
    rows = conn.execute(
        f"""
        SELECT b.*,c.name AS category_name
        FROM budgets b
        LEFT JOIN categories c ON c.id=b.category_id
        WHERE {' AND '.join(conditions)}
        ORDER BY b.period_type,c.name
        """,
        tuple(params),
    ).fetchall()
    result = []
    for row in rows:
        spent = _spent_for_budget(conn, row)
        remaining = row["limit_amount"] - spent
        usage = (spent / row["limit_amount"] * 100) if row["limit_amount"] else 0.0
        threshold = 0
        if usage >= 100:
            threshold = 100
        elif usage >= 90:
            threshold = 90
        elif usage >= 70:
            threshold = 70
        result.append(
            {
                "budget_id": row["id"],
                "category": row["category_name"] or "All categories",
                "period_type": row["period_type"],
                "start": row["start_date"],
                "end_exclusive": row["end_date"],
                "limit": row["limit_amount"],
                "limit_formatted": rupiah(row["limit_amount"]),
                "spent": spent,
                "spent_formatted": rupiah(spent),
                "remaining": remaining,
                "remaining_formatted": rupiah(remaining),
                "usage_percent": round(usage, 2),
                "usage_percent_formatted": percent(usage),
                "threshold": threshold,
                "over_budget": remaining < 0,
            }
        )
    conn.close()
    return result


def budget_cancel(budget_id: int) -> dict[str, Any]:
    conn = connect()
    cursor = conn.execute("UPDATE budgets SET active=0 WHERE id=?", (budget_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise ValueError(f"Budget #{budget_id} not found.")
    conn.commit()
    conn.close()
    return {"ok": True, "budget_id": budget_id, "active": False}
