from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

from .config import TZ
from .db import connect
from .ledger import create_transaction, parse_occurrence, resolve_category, resolve_wallet, wallet_balance
from .money import parse_amount, rupiah


def _status_for(remaining: int, original: int, due_date: str | None) -> str:
    if remaining <= 0:
        return "paid"
    if due_date and date.fromisoformat(due_date) < datetime.now(TZ).date():
        return "overdue"
    if remaining < original:
        return "partial"
    return "open"


def refresh_obligation_statuses(conn=None) -> int:
    owns = conn is None
    conn = conn or connect()
    rows = conn.execute(
        "SELECT id,original_amount,remaining_amount,due_date,status FROM obligations WHERE status NOT IN ('paid','cancelled')"
    ).fetchall()
    changed = 0
    for row in rows:
        status = _status_for(row["remaining_amount"], row["original_amount"], row["due_date"])
        if status != row["status"]:
            conn.execute("UPDATE obligations SET status=? WHERE id=?", (status, row["id"]))
            changed += 1
    if owns:
        conn.commit()
        conn.close()
    return changed


def obligation_add(
    *,
    kind: str,
    name: str,
    amount_raw: str | int,
    due_date: str | None = None,
    counterparty: str | None = None,
    category_name: str | None = None,
    default_wallet: str | None = None,
    note: str | None = None,
    raw_input: str | None = None,
    cash_wallet: str | None = None,
    date_raw: str | None = None,
) -> dict[str, Any]:
    if kind not in {"bill", "debt_payable", "debt_receivable"}:
        raise ValueError("Jenis kewajiban tidak valid.")
    amount = parse_amount(amount_raw)
    conn = connect()
    category_id = None
    category_label = None
    if kind == "bill":
        if not category_name:
            conn.close()
            raise ValueError("Tagihan wajib memiliki kategori pengeluaran.")
        category = resolve_category(conn, category_name, "expense")
        category_id = category["id"]
        category_label = category["name"]
    elif category_name:
        category = resolve_category(conn, category_name)
        category_id = category["id"]
        category_label = category["name"]

    default_wallet_id = None
    default_wallet_label = None
    if default_wallet:
        wallet = resolve_wallet(conn, default_wallet)
        default_wallet_id = wallet["id"]
        default_wallet_label = wallet["name"]

    now = datetime.now(TZ).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO obligations(
            kind,name,counterparty,original_amount,remaining_amount,category_id,
            default_wallet_id,due_date,status,note,raw_input,created_at
        ) VALUES(?,?,?,?,?,?,?,?, 'open',?,?,?)
        """,
        (
            kind,
            name.strip(),
            counterparty,
            amount,
            amount,
            category_id,
            default_wallet_id,
            due_date,
            note,
            raw_input,
            now,
        ),
    )
    obligation_id = int(cursor.lastrowid)
    cash_transaction_id = None
    cash_balance = None
    cash_wallet_label = None
    if cash_wallet:
        wallet = resolve_wallet(conn, cash_wallet)
        cash_wallet_label = wallet["name"]
        occurred_at = parse_occurrence(date_raw)
        if kind == "debt_payable":
            tx_type = "debt_draw"
            description = f"Dana utang diterima: {name.strip()}"
        elif kind == "debt_receivable":
            tx_type = "loan_given"
            description = f"Uang dipinjamkan: {name.strip()}"
        else:
            conn.close()
            raise ValueError("cash-wallet hanya berlaku untuk utang/piutang, bukan tagihan.")
        cash_transaction_id = create_transaction(
            conn,
            tx_type=tx_type,
            amount=amount,
            wallet_id=wallet["id"],
            description=description,
            occurred_at=occurred_at,
            note=f"Obligation #{obligation_id}",
            raw_input=raw_input,
            source="obligation",
            metadata={"obligation_id": obligation_id},
        )
        cash_balance = wallet_balance(conn, wallet["id"])
    refresh_obligation_statuses(conn)
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "obligation_id": obligation_id,
        "kind": kind,
        "name": name.strip(),
        "counterparty": counterparty,
        "amount": amount,
        "amount_formatted": rupiah(amount),
        "remaining": amount,
        "remaining_formatted": rupiah(amount),
        "due_date": due_date,
        "category": category_label,
        "default_wallet": default_wallet_label,
        "cash_transaction_id": cash_transaction_id,
        "cash_wallet": cash_wallet_label,
        "cash_wallet_balance": cash_balance,
        "cash_wallet_balance_formatted": rupiah(cash_balance) if cash_balance is not None else None,
        "status": "open",
    }


def obligation_pay(
    *,
    obligation_id: int,
    amount_raw: str | int,
    wallet_name: str,
    date_raw: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    refresh_obligation_statuses(conn)
    row = conn.execute(
        "SELECT * FROM obligations WHERE id=?", (obligation_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Tagihan/utang #{obligation_id} tidak ditemukan.")
    if row["status"] in {"paid", "cancelled"}:
        conn.close()
        raise ValueError("Tagihan/utang ini sudah ditutup.")
    amount = parse_amount(amount_raw)
    if amount > row["remaining_amount"]:
        conn.close()
        raise ValueError("Pembayaran melebihi sisa kewajiban/piutang.")
    wallet = resolve_wallet(conn, wallet_name)
    occurred_at = parse_occurrence(date_raw)
    if row["kind"] == "bill":
        tx_type = "expense"
        category_id = row["category_id"]
        description = f"Bayar tagihan: {row['name']}"
    elif row["kind"] == "debt_payable":
        tx_type = "debt_repayment"
        category_id = None
        description = f"Bayar utang: {row['name']}"
    else:
        tx_type = "loan_collection"
        category_id = None
        description = f"Terima pembayaran piutang: {row['name']}"
    tx_id = create_transaction(
        conn,
        tx_type=tx_type,
        amount=amount,
        wallet_id=wallet["id"],
        category_id=category_id,
        description=description,
        occurred_at=occurred_at,
        note=note,
        source="obligation",
        metadata={"obligation_id": obligation_id},
    )
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO obligation_payments(obligation_id,transaction_id,amount,paid_at,wallet_id,note)
        VALUES(?,?,?,?,?,?)
        """,
        (obligation_id, tx_id, amount, occurred_at, wallet["id"], note),
    )
    remaining = row["remaining_amount"] - amount
    status = _status_for(remaining, row["original_amount"], row["due_date"])
    closed_at = now if status == "paid" else None
    conn.execute(
        "UPDATE obligations SET remaining_amount=?,status=?,closed_at=? WHERE id=?",
        (remaining, status, closed_at, obligation_id),
    )
    conn.commit()
    balance = wallet_balance(conn, wallet["id"])
    conn.close()
    return {
        "ok": True,
        "obligation_id": obligation_id,
        "transaction_id": tx_id,
        "kind": row["kind"],
        "name": row["name"],
        "paid": amount,
        "paid_formatted": rupiah(amount),
        "remaining": remaining,
        "remaining_formatted": rupiah(remaining),
        "status": status,
        "wallet": wallet["name"],
        "wallet_balance": balance,
        "wallet_balance_formatted": rupiah(balance),
        "occurred_at": occurred_at,
    }


def obligations_list(
    *,
    kind: str | None = None,
    status: str | None = None,
    due_before: str | None = None,
) -> list[dict[str, Any]]:
    conn = connect()
    refresh_obligation_statuses(conn)
    conn.commit()
    conditions = []
    params: list[Any] = []
    if kind:
        conditions.append("o.kind=?")
        params.append(kind)
    if status:
        conditions.append("o.status=?")
        params.append(status)
    if due_before:
        conditions.append("o.due_date<=?")
        params.append(due_before)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""
        SELECT o.*,c.name AS category,w.name AS default_wallet
        FROM obligations o
        LEFT JOIN categories c ON c.id=o.category_id
        LEFT JOIN wallets w ON w.id=o.default_wallet_id
        {where}
        ORDER BY CASE o.status WHEN 'overdue' THEN 0 WHEN 'open' THEN 1 WHEN 'partial' THEN 2 ELSE 3 END,
                 o.due_date,o.id
        """,
        tuple(params),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["original_amount_formatted"] = rupiah(item["original_amount"])
        item["remaining_amount_formatted"] = rupiah(item["remaining_amount"])
        result.append(item)
    return result


def obligation_cancel(obligation_id: int, reason: str) -> dict[str, Any]:
    conn = connect()
    row = conn.execute("SELECT status FROM obligations WHERE id=?", (obligation_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Tagihan/utang #{obligation_id} tidak ditemukan.")
    if row["status"] == "paid":
        conn.close()
        raise ValueError("Kewajiban yang sudah lunas tidak dapat dibatalkan.")
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE obligations SET status='cancelled',closed_at=?,note=COALESCE(note,'') || ? WHERE id=?",
        (now, f" | Cancelled: {reason.strip()}", obligation_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "obligation_id": obligation_id, "status": "cancelled"}


def _add_months(current: date, months: int) -> date:
    month_index = current.month - 1 + months
    year = current.year + month_index // 12
    month = month_index % 12 + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _advance_due(current: date, frequency: str, interval_count: int) -> date:
    if frequency == "weekly":
        return current + timedelta(weeks=interval_count)
    if frequency == "monthly":
        return _add_months(current, interval_count)
    if frequency == "yearly":
        return _add_months(current, 12 * interval_count)
    raise ValueError("Frekuensi tidak valid.")


def recurring_add(
    *,
    name: str,
    amount_raw: str | int,
    category_name: str,
    next_due_date: str,
    frequency: str = "monthly",
    interval_count: int = 1,
    default_wallet: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if frequency not in {"weekly", "monthly", "yearly"}:
        raise ValueError("Frekuensi harus weekly, monthly, atau yearly.")
    if interval_count <= 0:
        raise ValueError("Interval harus lebih dari 0.")
    date.fromisoformat(next_due_date)
    amount = parse_amount(amount_raw)
    conn = connect()
    category = resolve_category(conn, category_name, "expense")
    wallet_id = None
    wallet_label = None
    if default_wallet:
        wallet = resolve_wallet(conn, default_wallet)
        wallet_id = wallet["id"]
        wallet_label = wallet["name"]
    now = datetime.now(TZ).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO recurring_rules(
            name,amount,category_id,default_wallet_id,frequency,interval_count,
            next_due_date,active,note,created_at
        ) VALUES(?,?,?,?,?,?,?,1,?,?)
        """,
        (
            name.strip(),
            amount,
            category["id"],
            wallet_id,
            frequency,
            interval_count,
            next_due_date,
            note,
            now,
        ),
    )
    conn.commit()
    rule_id = cursor.lastrowid
    conn.close()
    return {
        "ok": True,
        "rule_id": rule_id,
        "name": name.strip(),
        "amount": amount,
        "amount_formatted": rupiah(amount),
        "category": category["name"],
        "default_wallet": wallet_label,
        "frequency": frequency,
        "interval_count": interval_count,
        "next_due_date": next_due_date,
    }


def recurring_run(until_date: str | None = None) -> dict[str, Any]:
    until = date.fromisoformat(until_date) if until_date else datetime.now(TZ).date()
    conn = connect()
    rules = conn.execute("SELECT * FROM recurring_rules WHERE active=1 ORDER BY id").fetchall()
    created = []
    now = datetime.now(TZ).isoformat(timespec="seconds")
    for rule in rules:
        due = date.fromisoformat(rule["next_due_date"])
        while due <= until:
            existing = conn.execute(
                "SELECT obligation_id FROM recurring_occurrences WHERE rule_id=? AND due_date=?",
                (rule["id"], due.isoformat()),
            ).fetchone()
            if not existing:
                cursor = conn.execute(
                    """
                    INSERT INTO obligations(
                        kind,name,original_amount,remaining_amount,category_id,default_wallet_id,
                        due_date,status,recurring_rule_id,note,created_at
                    ) VALUES('bill',?,?,?,?,?,?, 'open',?,?,?)
                    """,
                    (
                        f"{rule['name']} ({due.isoformat()})",
                        rule["amount"],
                        rule["amount"],
                        rule["category_id"],
                        rule["default_wallet_id"],
                        due.isoformat(),
                        rule["id"],
                        rule["note"],
                        now,
                    ),
                )
                obligation_id = int(cursor.lastrowid)
                conn.execute(
                    """
                    INSERT INTO recurring_occurrences(rule_id,due_date,obligation_id,created_at)
                    VALUES(?,?,?,?)
                    """,
                    (rule["id"], due.isoformat(), obligation_id, now),
                )
                created.append(
                    {
                        "rule_id": rule["id"],
                        "obligation_id": obligation_id,
                        "name": rule["name"],
                        "due_date": due.isoformat(),
                        "amount": rule["amount"],
                        "amount_formatted": rupiah(rule["amount"]),
                    }
                )
            due = _advance_due(due, rule["frequency"], rule["interval_count"])
        conn.execute(
            "UPDATE recurring_rules SET next_due_date=? WHERE id=?",
            (due.isoformat(), rule["id"]),
        )
    refresh_obligation_statuses(conn)
    conn.commit()
    conn.close()
    return {"ok": True, "until_date": until.isoformat(), "created_count": len(created), "created": created}


def recurring_list() -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        """
        SELECT r.*,c.name AS category,w.name AS default_wallet
        FROM recurring_rules r
        JOIN categories c ON c.id=r.category_id
        LEFT JOIN wallets w ON w.id=r.default_wallet_id
        ORDER BY r.active DESC,r.next_due_date,r.id
        """
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["amount_formatted"] = rupiah(item["amount"])
        result.append(item)
    return result


def recurring_pause(rule_id: int, active: bool) -> dict[str, Any]:
    conn = connect()
    cursor = conn.execute("UPDATE recurring_rules SET active=? WHERE id=?", (1 if active else 0, rule_id))
    if cursor.rowcount == 0:
        conn.close()
        raise ValueError(f"Aturan berulang #{rule_id} tidak ditemukan.")
    conn.commit()
    conn.close()
    return {"ok": True, "rule_id": rule_id, "active": active}
