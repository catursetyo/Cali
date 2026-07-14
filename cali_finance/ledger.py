from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Any

from .config import TZ
from .db import connect
from .money import normalize, parse_amount, parse_signed_amount, rupiah

TRANSACTION_TYPES = {
    "expense",
    "income",
    "transfer",
    "adjustment_in",
    "adjustment_out",
    "debt_draw",
    "debt_repayment",
    "loan_given",
    "loan_collection",
}

BALANCE_IN_TYPES = {"income", "adjustment_in", "debt_draw", "loan_collection"}
BALANCE_OUT_TYPES = {"expense", "adjustment_out", "debt_repayment", "loan_given"}


def parse_occurrence(raw: str | None) -> str:
    now = datetime.now(TZ)
    if not raw:
        return now.isoformat(timespec="seconds")

    raw = raw.strip()
    try:
        if len(raw) == 10:
            parsed_date = date.fromisoformat(raw)
            return datetime.combine(parsed_date, now.timetz(), tzinfo=TZ).isoformat(timespec="seconds")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        return parsed.astimezone(TZ).isoformat(timespec="seconds")
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD or ISO-8601 format.") from exc


def resolve_wallet(conn: sqlite3.Connection, value: str) -> sqlite3.Row:
    key = normalize(value)
    row = conn.execute(
        """
        SELECT w.* FROM wallet_aliases a
        JOIN wallets w ON w.id=a.wallet_id
        WHERE a.alias=? COLLATE NOCASE AND w.active=1
        """,
        (key,),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT * FROM wallets WHERE name=? COLLATE NOCASE AND active=1",
            (value.strip(),),
        ).fetchone()
    if not row:
        raise ValueError(
            f"Wallet {value!r} is not registered. Add it with wallet-add."
        )
    return row


def resolve_category(
    conn: sqlite3.Connection, value: str, expected_type: str | None = None
) -> sqlite3.Row:
    key = normalize(value)
    params: list[Any] = [key]
    type_clause = ""
    if expected_type:
        type_clause = " AND c.type=?"
        params.append(expected_type)
    row = conn.execute(
        f"""
        SELECT c.* FROM category_aliases a
        JOIN categories c ON c.id=a.category_id
        WHERE a.alias=? COLLATE NOCASE AND c.active=1 {type_clause}
        """,
        tuple(params),
    ).fetchone()
    if not row:
        params = [value.strip()]
        type_clause = ""
        if expected_type:
            type_clause = " AND type=?"
            params.append(expected_type)
        row = conn.execute(
            f"SELECT * FROM categories WHERE name=? COLLATE NOCASE AND active=1 {type_clause}",
            tuple(params),
        ).fetchone()
    if not row:
        suffix = f" as {expected_type}" if expected_type else ""
        raise ValueError(
            f"Category {value!r} is not registered{suffix}. Add it with category-add."
        )
    return row


def infer_category(
    conn: sqlite3.Connection, description: str, expected_type: str
) -> sqlite3.Row | None:
    text = normalize(description)
    rows = conn.execute(
        """
        SELECT c.*, a.alias
        FROM category_aliases a
        JOIN categories c ON c.id=a.category_id
        WHERE c.type=? AND c.active=1
        ORDER BY LENGTH(a.alias) DESC
        """,
        (expected_type,),
    ).fetchall()
    for row in rows:
        alias = normalize(row["alias"])
        if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text):
            return row
    return None


def wallet_balance(conn: sqlite3.Connection, wallet_id: int) -> int:
    wallet = conn.execute(
        "SELECT opening_balance FROM wallets WHERE id=?", (wallet_id,)
    ).fetchone()
    if not wallet:
        raise ValueError("Wallet not found.")

    rows = conn.execute(
        """
        SELECT type, amount, wallet_id, to_wallet_id
        FROM transactions
        WHERE status='active' AND (wallet_id=? OR to_wallet_id=?)
        """,
        (wallet_id, wallet_id),
    ).fetchall()
    balance = wallet["opening_balance"]
    for row in rows:
        tx_type = row["type"]
        if tx_type == "transfer":
            if row["wallet_id"] == wallet_id:
                balance -= row["amount"]
            if row["to_wallet_id"] == wallet_id:
                balance += row["amount"]
        elif row["wallet_id"] == wallet_id:
            if tx_type in BALANCE_IN_TYPES:
                balance += row["amount"]
            elif tx_type in BALANCE_OUT_TYPES:
                balance -= row["amount"]
    return balance


def all_wallet_balances(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM wallets WHERE active=1 ORDER BY name"
    ).fetchall()
    result = []
    for row in rows:
        balance = wallet_balance(conn, row["id"])
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "kind": row["kind"],
                "opening_balance": row["opening_balance"],
                "opening_balance_formatted": rupiah(row["opening_balance"]),
                "balance": balance,
                "balance_formatted": rupiah(balance),
            }
        )
    return result


def _fingerprint(
    occurred_at: str,
    tx_type: str,
    amount: int,
    wallet_id: int,
    category_id: int | None,
    description: str,
) -> str:
    day = occurred_at[:10]
    clean_description = re.sub(r"[^a-z0-9 ]+", "", normalize(description))
    clean_description = " ".join(sorted(clean_description.split()))
    raw = f"{day}|{tx_type}|{amount}|{wallet_id}|{category_id or 0}|{clean_description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def duplicate_candidates(
    conn: sqlite3.Connection,
    *,
    occurred_at: str,
    tx_type: str,
    amount: int,
    wallet_id: int,
    category_id: int | None,
    description: str,
    window_days: int = 1,
) -> list[dict[str, Any]]:
    anchor = date.fromisoformat(occurred_at[:10])
    start = datetime.combine(anchor - timedelta(days=window_days), time.min, TZ)
    end = datetime.combine(anchor + timedelta(days=window_days + 1), time.min, TZ)
    rows = conn.execute(
        """
        SELECT t.id, t.occurred_at, t.amount, t.description, t.type,
               w.name AS wallet, c.name AS category
        FROM transactions t
        JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN categories c ON c.id=t.category_id
        WHERE t.status='active'
          AND t.type=?
          AND t.amount=?
          AND t.wallet_id=?
          AND COALESCE(t.category_id,0)=COALESCE(?,0)
          AND t.occurred_at>=?
          AND t.occurred_at<?
        ORDER BY t.occurred_at DESC
        """,
        (
            tx_type,
            amount,
            wallet_id,
            category_id,
            start.isoformat(timespec="seconds"),
            end.isoformat(timespec="seconds"),
        ),
    ).fetchall()

    target = normalize(description)
    candidates = []
    for row in rows:
        ratio = difflib.SequenceMatcher(None, target, normalize(row["description"])).ratio()
        if ratio >= 0.72:
            item = dict(row)
            item["similarity"] = round(ratio, 3)
            item["amount_formatted"] = rupiah(item["amount"])
            candidates.append(item)
    return candidates


def _validate_type_fields(
    tx_type: str,
    category_id: int | None,
    wallet_id: int,
    to_wallet_id: int | None,
) -> None:
    if tx_type not in TRANSACTION_TYPES:
        raise ValueError(f"Invalid transaction type: {tx_type}")
    if tx_type in {"expense", "income"} and category_id is None:
        raise ValueError("Expenses and income require a category.")
    if tx_type == "transfer":
        if to_wallet_id is None:
            raise ValueError("Transfers require a destination wallet.")
        if wallet_id == to_wallet_id:
            raise ValueError("Source and destination wallets must be different.")
    elif to_wallet_id is not None:
        raise ValueError("A destination wallet may only be used for transfers.")


def create_transaction(
    conn: sqlite3.Connection,
    *,
    tx_type: str,
    amount: int,
    wallet_id: int,
    description: str,
    occurred_at: str,
    category_id: int | None = None,
    to_wallet_id: int | None = None,
    note: str | None = None,
    raw_input: str | None = None,
    source: str = "hermes",
    external_id: str | None = None,
    import_batch_id: int | None = None,
    receipt_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    _validate_type_fields(tx_type, category_id, wallet_id, to_wallet_id)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    fingerprint = _fingerprint(
        occurred_at, tx_type, amount, wallet_id, category_id, description
    )
    try:
        cursor = conn.execute(
            """
            INSERT INTO transactions(
                occurred_at, type, amount, category_id, wallet_id, to_wallet_id,
                description, note, raw_input, source, status, created_at,
                fingerprint, external_id, import_batch_id, receipt_id, metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?, 'active', ?,?,?,?,?,?)
            """,
            (
                occurred_at,
                tx_type,
                amount,
                category_id,
                wallet_id,
                to_wallet_id,
                description.strip(),
                note,
                raw_input,
                source,
                now,
                fingerprint,
                external_id,
                import_batch_id,
                receipt_id,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if external_id and "external_id" in str(exc).lower():
            raise ValueError(f"External ID {external_id!r} has already been imported.") from exc
        raise
    return int(cursor.lastrowid)


def add_transaction(
    *,
    tx_type: str,
    amount_raw: str | int,
    wallet_name: str,
    description: str,
    category_name: str | None = None,
    date_raw: str | None = None,
    note: str | None = None,
    raw_input: str | None = None,
    source: str = "hermes",
    force_duplicate: bool = False,
    external_id: str | None = None,
    import_batch_id: int | None = None,
    receipt_id: int | None = None,
) -> dict[str, Any]:
    if tx_type not in {"expense", "income"}:
        raise ValueError("Use add only for expense or income transactions.")
    conn = connect()
    wallet = resolve_wallet(conn, wallet_name)
    if category_name:
        category = resolve_category(conn, category_name, tx_type)
    else:
        category = infer_category(conn, description, tx_type)
        if not category:
            conn.close()
            raise ValueError(
                "Category is unclear. Specify a category before recording the transaction."
            )
    amount = parse_amount(amount_raw)
    occurred_at = parse_occurrence(date_raw)

    duplicates = duplicate_candidates(
        conn,
        occurred_at=occurred_at,
        tx_type=tx_type,
        amount=amount,
        wallet_id=wallet["id"],
        category_id=category["id"],
        description=description,
    )
    if duplicates and not force_duplicate:
        conn.close()
        return {
            "ok": False,
            "code": "possible_duplicate",
            "message": "A similar transaction exists. Ask for confirmation before using --force-duplicate.",
            "candidates": duplicates,
        }

    tx_id = create_transaction(
        conn,
        tx_type=tx_type,
        amount=amount,
        wallet_id=wallet["id"],
        category_id=category["id"],
        description=description,
        occurred_at=occurred_at,
        note=note,
        raw_input=raw_input,
        source=source,
        external_id=external_id,
        import_batch_id=import_batch_id,
        receipt_id=receipt_id,
    )
    conn.commit()
    balance = wallet_balance(conn, wallet["id"])
    conn.close()
    from .budgets import budget_status
    active_budgets = [
        item for item in budget_status(anchor_date=occurred_at[:10])
        if item["category"] in {category["name"], "All categories"}
    ] if tx_type == "expense" else []
    warnings = [item for item in active_budgets if item["threshold"]]
    return {
        "ok": True,
        "transaction_id": tx_id,
        "type": tx_type,
        "amount": amount,
        "amount_formatted": rupiah(amount),
        "category": category["name"],
        "wallet": wallet["name"],
        "description": description.strip(),
        "occurred_at": occurred_at,
        "wallet_balance": balance,
        "wallet_balance_formatted": rupiah(balance),
        "duplicate_override": bool(duplicates),
        "budget_status": active_budgets,
        "budget_warnings": warnings,
    }


def transfer(
    *,
    amount_raw: str | int,
    from_wallet_name: str,
    to_wallet_name: str,
    description: str,
    date_raw: str | None = None,
    note: str | None = None,
    raw_input: str | None = None,
    source: str = "hermes",
) -> dict[str, Any]:
    conn = connect()
    source_wallet = resolve_wallet(conn, from_wallet_name)
    destination = resolve_wallet(conn, to_wallet_name)
    amount = parse_amount(amount_raw)
    occurred_at = parse_occurrence(date_raw)
    tx_id = create_transaction(
        conn,
        tx_type="transfer",
        amount=amount,
        wallet_id=source_wallet["id"],
        to_wallet_id=destination["id"],
        description=description,
        occurred_at=occurred_at,
        note=note,
        raw_input=raw_input,
        source=source,
    )
    conn.commit()
    from_balance = wallet_balance(conn, source_wallet["id"])
    to_balance = wallet_balance(conn, destination["id"])
    conn.close()
    return {
        "ok": True,
        "transaction_id": tx_id,
        "type": "transfer",
        "amount": amount,
        "amount_formatted": rupiah(amount),
        "from_wallet": source_wallet["name"],
        "to_wallet": destination["name"],
        "occurred_at": occurred_at,
        "from_wallet_balance": from_balance,
        "from_wallet_balance_formatted": rupiah(from_balance),
        "to_wallet_balance": to_balance,
        "to_wallet_balance_formatted": rupiah(to_balance),
    }


def wallet_add(
    name: str,
    kind: str,
    opening_balance_raw: str | int,
    aliases: str | None,
) -> dict[str, Any]:
    if kind not in {"cash", "bank", "ewallet", "other"}:
        raise ValueError("Invalid wallet type.")
    conn = connect()
    now = datetime.now(TZ).isoformat(timespec="seconds")
    opening = parse_signed_amount(opening_balance_raw)
    try:
        cursor = conn.execute(
            "INSERT INTO wallets(name, kind, opening_balance, created_at) VALUES(?,?,?,?)",
            (name.strip(), kind, opening, now),
        )
    except sqlite3.IntegrityError as exc:
        conn.close()
        raise ValueError(f"Wallet {name!r} already exists.") from exc
    wallet_id = cursor.lastrowid
    alias_values = [name] + (aliases.split(",") if aliases else [])
    for alias in alias_values:
        key = normalize(alias)
        if key:
            conn.execute(
                "INSERT OR REPLACE INTO wallet_aliases(alias, wallet_id) VALUES(?,?)",
                (key, wallet_id),
            )
    conn.commit()
    conn.close()
    return {"ok": True, "wallet_id": wallet_id, "wallet": name.strip()}


def wallet_set(
    name: str,
    kind: str | None = None,
    opening_balance_raw: str | int | None = None,
    aliases: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    wallet = resolve_wallet(conn, name)
    updates = []
    params: list[Any] = []
    if kind is not None:
        if kind not in {"cash", "bank", "ewallet", "other"}:
            conn.close()
            raise ValueError("Invalid wallet type.")
        updates.append("kind=?")
        params.append(kind)
    if opening_balance_raw is not None:
        updates.append("opening_balance=?")
        params.append(parse_signed_amount(opening_balance_raw))
    if updates:
        params.append(wallet["id"])
        conn.execute(
            f"UPDATE wallets SET {', '.join(updates)} WHERE id=?", tuple(params)
        )
    if aliases:
        for alias in aliases.split(","):
            key = normalize(alias)
            if key:
                conn.execute(
                    "INSERT OR REPLACE INTO wallet_aliases(alias, wallet_id) VALUES(?,?)",
                    (key, wallet["id"]),
                )
    conn.commit()
    updated = conn.execute("SELECT * FROM wallets WHERE id=?", (wallet["id"],)).fetchone()
    balance = wallet_balance(conn, wallet["id"])
    conn.close()
    return {
        "ok": True,
        "wallet": updated["name"],
        "kind": updated["kind"],
        "opening_balance": updated["opening_balance"],
        "opening_balance_formatted": rupiah(updated["opening_balance"]),
        "balance": balance,
        "balance_formatted": rupiah(balance),
    }


def category_add(
    name: str, category_type: str, aliases: str | None
) -> dict[str, Any]:
    if category_type not in {"expense", "income"}:
        raise ValueError("Category type must be expense or income.")
    conn = connect()
    now = datetime.now(TZ).isoformat(timespec="seconds")
    try:
        cursor = conn.execute(
            "INSERT INTO categories(name, type, created_at) VALUES(?,?,?)",
            (name.strip(), category_type, now),
        )
    except sqlite3.IntegrityError as exc:
        conn.close()
        raise ValueError(f"Category {name!r} already exists.") from exc
    category_id = cursor.lastrowid
    alias_values = [name] + (aliases.split(",") if aliases else [])
    for alias in alias_values:
        key = normalize(alias)
        if key:
            conn.execute(
                "INSERT OR REPLACE INTO category_aliases(alias, category_id) VALUES(?,?)",
                (key, category_id),
            )
    conn.commit()
    conn.close()
    return {"ok": True, "category_id": category_id, "category": name.strip()}


def categories(category_type: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    if category_type:
        rows = conn.execute(
            "SELECT id,name,type FROM categories WHERE active=1 AND type=? ORDER BY name",
            (category_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,name,type FROM categories WHERE active=1 ORDER BY type,name"
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def recent_transactions(limit: int = 20) -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        """
        SELECT t.id,t.occurred_at,t.type,t.amount,t.description,t.status,
               c.name AS category,w.name AS wallet,tw.name AS to_wallet,
               t.source,t.external_id
        FROM transactions t
        LEFT JOIN categories c ON c.id=t.category_id
        JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN wallets tw ON tw.id=t.to_wallet_id
        ORDER BY t.occurred_at DESC,t.id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["amount_formatted"] = rupiah(item["amount"])
        result.append(item)
    return result


def search_transactions(
    *,
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_amount: str | int | None = None,
    max_amount: str | int | None = None,
    category_name: str | None = None,
    wallet_name: str | None = None,
    tx_type: str | None = None,
    status: str = "active",
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = connect()
    conditions = ["t.status=?"]
    params: list[Any] = [status]
    if query:
        conditions.append("LOWER(t.description) LIKE ?")
        params.append(f"%{normalize(query)}%")
    if date_from:
        start_date = date.fromisoformat(date_from)
        conditions.append("t.occurred_at>=?")
        params.append(datetime.combine(start_date, time.min, TZ).isoformat(timespec="seconds"))
    if date_to:
        end_date = date.fromisoformat(date_to) + timedelta(days=1)
        conditions.append("t.occurred_at<?")
        params.append(datetime.combine(end_date, time.min, TZ).isoformat(timespec="seconds"))
    if min_amount is not None:
        conditions.append("t.amount>=?")
        params.append(parse_amount(min_amount, allow_zero=True))
    if max_amount is not None:
        conditions.append("t.amount<=?")
        params.append(parse_amount(max_amount, allow_zero=True))
    if category_name:
        category = resolve_category(conn, category_name)
        conditions.append("t.category_id=?")
        params.append(category["id"])
    if wallet_name:
        wallet = resolve_wallet(conn, wallet_name)
        conditions.append("(t.wallet_id=? OR t.to_wallet_id=?)")
        params.extend([wallet["id"], wallet["id"]])
    if tx_type:
        conditions.append("t.type=?")
        params.append(tx_type)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT t.id,t.occurred_at,t.type,t.amount,t.description,t.status,
               c.name AS category,w.name AS wallet,tw.name AS to_wallet,
               t.note,t.source,t.external_id
        FROM transactions t
        LEFT JOIN categories c ON c.id=t.category_id
        JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN wallets tw ON tw.id=t.to_wallet_id
        WHERE {' AND '.join(conditions)}
        ORDER BY t.occurred_at DESC,t.id DESC LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    conn.close()
    output = []
    for row in rows:
        item = dict(row)
        item["amount_formatted"] = rupiah(item["amount"])
        output.append(item)
    return output


def void_transaction(transaction_id: int, reason: str) -> dict[str, Any]:
    conn = connect()
    row = conn.execute(
        "SELECT id,status FROM transactions WHERE id=?", (transaction_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Transaction #{transaction_id} not found.")
    if row["status"] == "void":
        conn.close()
        raise ValueError(f"Transaction #{transaction_id} has already been voided.")
    now = datetime.now(TZ).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE transactions SET status='void',voided_at=?,void_reason=? WHERE id=?",
        (now, reason.strip(), transaction_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "transaction_id": transaction_id, "status": "void"}


def reconcile_preview(
    wallet_name: str,
    actual_balance_raw: str | int,
    note: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    wallet = resolve_wallet(conn, wallet_name)
    recorded = wallet_balance(conn, wallet["id"])
    actual = parse_signed_amount(actual_balance_raw)
    difference = actual - recorded
    now = datetime.now(TZ).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO balance_checks(
            wallet_id,recorded_balance,actual_balance,difference,checked_at,note,status
        ) VALUES(?,?,?,?,?,?, 'pending')
        """,
        (wallet["id"], recorded, actual, difference, now, note),
    )
    conn.commit()
    check_id = cursor.lastrowid
    conn.close()
    return {
        "ok": True,
        "check_id": check_id,
        "wallet": wallet["name"],
        "recorded_balance": recorded,
        "recorded_balance_formatted": rupiah(recorded),
        "actual_balance": actual,
        "actual_balance_formatted": rupiah(actual),
        "difference": difference,
        "difference_formatted": rupiah(difference),
        "requires_confirmation": difference != 0,
    }


def reconcile_adjust(
    check_id: int,
    reason: str,
    confirm_adjust: str,
) -> dict[str, Any]:
    if confirm_adjust != "YES":
        raise ValueError("Adjustment requires --confirm-adjust YES.")
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    check = conn.execute(
        """
        SELECT bc.*,w.name AS wallet_name
        FROM balance_checks bc JOIN wallets w ON w.id=bc.wallet_id
        WHERE bc.id=?
        """,
        (check_id,),
    ).fetchone()
    if not check:
        conn.close()
        raise ValueError(f"Balance check #{check_id} not found.")
    if check["status"] != "pending":
        conn.close()
        raise ValueError("This balance check has already been closed.")
    current_balance = wallet_balance(conn, check["wallet_id"])
    difference = check["actual_balance"] - current_balance
    revalidation_note = ""
    if current_balance != check["recorded_balance"]:
        revalidation_note = (
            f" | Revalidated: recorded {check['recorded_balance']} -> {current_balance}, "
            f"difference {check['difference']} -> {difference}"
        )
    if difference == 0:
        conn.execute(
            """
            UPDATE balance_checks
            SET recorded_balance=?,difference=?,status='closed',
                note=COALESCE(note,'') || ?
            WHERE id=?
            """,
            (current_balance, difference, revalidation_note, check_id),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "check_id": check_id, "status": "closed", "adjustment": 0}
    tx_type = "adjustment_in" if difference > 0 else "adjustment_out"
    amount = abs(difference)
    occurred_at = datetime.now(TZ).isoformat(timespec="seconds")
    tx_id = create_transaction(
        conn,
        tx_type=tx_type,
        amount=amount,
        wallet_id=check["wallet_id"],
        description=f"Balance adjustment: {reason.strip()}",
        occurred_at=occurred_at,
        note=f"Balance check #{check_id}",
        source="reconciliation",
        metadata={"balance_check_id": check_id},
    )
    conn.execute(
        """
        UPDATE balance_checks
        SET recorded_balance=?,difference=?,status='adjusted',
            adjustment_transaction_id=?,note=COALESCE(note,'') || ?
        WHERE id=?
        """,
        (
            current_balance,
            difference,
            tx_id,
            revalidation_note + f" | Adjustment: {reason.strip()}",
            check_id,
        ),
    )
    new_balance = wallet_balance(conn, check["wallet_id"])
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "check_id": check_id,
        "transaction_id": tx_id,
        "wallet": check["wallet_name"],
        "adjustment_type": tx_type,
        "adjustment": amount,
        "adjustment_formatted": rupiah(amount),
        "new_balance": new_balance,
        "new_balance_formatted": rupiah(new_balance),
    }


def reconcile_close(check_id: int, reason: str) -> dict[str, Any]:
    conn = connect()
    row = conn.execute(
        "SELECT status FROM balance_checks WHERE id=?", (check_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Balance check #{check_id} not found.")
    if row["status"] != "pending":
        conn.close()
        raise ValueError("This balance check has already been closed.")
    conn.execute(
        "UPDATE balance_checks SET status='closed',note=COALESCE(note,'') || ? WHERE id=?",
        (f" | Closed: {reason.strip()}", check_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "check_id": check_id, "status": "closed"}
