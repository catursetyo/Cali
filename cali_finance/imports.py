from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import IMPORT_DIR, TZ
from .db import connect
from .ledger import (
    create_transaction,
    duplicate_candidates,
    infer_category,
    parse_occurrence,
    resolve_category,
    resolve_wallet,
    wallet_balance,
)
from .money import normalize, parse_amount, parse_signed_amount, rupiah

DATE_CANDIDATES = ["date", "tanggal", "transaction date", "trx date", "waktu"]
DESC_CANDIDATES = ["description", "keterangan", "details", "merchant", "uraian", "remark"]
AMOUNT_CANDIDATES = ["amount", "nominal", "jumlah", "value"]
DEBIT_CANDIDATES = ["debit", "keluar", "withdrawal", "expense"]
CREDIT_CANDIDATES = ["credit", "masuk", "deposit", "income"]
TYPE_CANDIDATES = ["type", "jenis", "direction", "debit/credit"]
EXTERNAL_ID_CANDIDATES = ["id", "transaction id", "reference", "ref", "no referensi"]
CATEGORY_CANDIDATES = ["category", "kategori"]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists() or not path.is_file():
        raise ValueError(f"CSV file not found: {path}")
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise ValueError("CSV has no header.")
                return list(reader.fieldnames), [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("CSV encoding could not be read.") from last_error


def _find_column(headers: list[str], explicit: str | None, candidates: list[str]) -> str | None:
    normalized = {normalize(header): header for header in headers}
    if explicit:
        key = normalize(explicit)
        if key not in normalized:
            raise ValueError(f"Column {explicit!r} not found in the CSV.")
        return normalized[key]
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _parse_date(raw: str, date_format: str | None) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("Date is empty.")
    if date_format:
        parsed = datetime.strptime(raw, date_format)
        return parsed.replace(tzinfo=TZ).isoformat(timespec="seconds")
    # ISO first, then common Indonesian bank export formats.
    for fmt in (None, "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            if fmt is None:
                return parse_occurrence(raw)
            return datetime.strptime(raw, fmt).replace(tzinfo=TZ).isoformat(timespec="seconds")
        except ValueError:
            continue
    raise ValueError(f"Date could not be parsed: {raw!r}")


def _direction(raw: str) -> str | None:
    value = normalize(raw)
    if value in {"debit", "expense", "keluar", "out", "d", "db"}:
        return "expense"
    if value in {"credit", "income", "masuk", "in", "c", "cr"}:
        return "income"
    return None


def import_preview(
    *,
    file_path: str,
    wallet_name: str,
    source_name: str,
    date_column: str | None = None,
    description_column: str | None = None,
    amount_column: str | None = None,
    debit_column: str | None = None,
    credit_column: str | None = None,
    type_column: str | None = None,
    external_id_column: str | None = None,
    category_column: str | None = None,
    date_format: str | None = None,
    positive_is: str = "income",
) -> dict[str, Any]:
    if positive_is not in {"income", "expense"}:
        raise ValueError("positive-is must be income or expense.")
    path = Path(file_path).expanduser().resolve()
    headers, rows = _read_csv(path)
    date_col = _find_column(headers, date_column, DATE_CANDIDATES)
    desc_col = _find_column(headers, description_column, DESC_CANDIDATES)
    amount_col = _find_column(headers, amount_column, AMOUNT_CANDIDATES)
    debit_col = _find_column(headers, debit_column, DEBIT_CANDIDATES)
    credit_col = _find_column(headers, credit_column, CREDIT_CANDIDATES)
    type_col = _find_column(headers, type_column, TYPE_CANDIDATES)
    external_col = _find_column(headers, external_id_column, EXTERNAL_ID_CANDIDATES)
    category_col = _find_column(headers, category_column, CATEGORY_CANDIDATES)
    if not date_col or not desc_col:
        raise ValueError("Date and description columns must be detected or specified explicitly.")
    if not amount_col and not debit_col and not credit_col:
        raise ValueError("An amount column or debit/credit pair is required.")

    conn = connect()
    wallet = resolve_wallet(conn, wallet_name)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    cursor = conn.execute(
        """
        INSERT INTO import_batches(source_name,file_path,wallet_id,status,created_at)
        VALUES(?,?,?,'preview',?)
        """,
        (source_name.strip(), str(path), wallet["id"], now),
    )
    batch_id = int(cursor.lastrowid)
    counters = {"ready": 0, "unresolved": 0, "duplicate": 0, "error": 0}
    preview_rows = []

    for index, raw_row in enumerate(rows, start=2):
        status = "ready"
        error = None
        occurred_at = None
        tx_type = None
        amount = None
        description = (raw_row.get(desc_col) or "").strip()
        category_id = None
        category_name = None
        external_id = None
        try:
            occurred_at = _parse_date(raw_row.get(date_col, ""), date_format)
            if type_col:
                tx_type = _direction(raw_row.get(type_col, ""))
            if debit_col or credit_col:
                debit_raw = (raw_row.get(debit_col, "") if debit_col else "").strip()
                credit_raw = (raw_row.get(credit_col, "") if credit_col else "").strip()
                debit = parse_amount(debit_raw, allow_zero=True) if debit_raw else 0
                credit = parse_amount(credit_raw, allow_zero=True) if credit_raw else 0
                if debit > 0 and credit > 0:
                    raise ValueError("Row contains both debit and credit values.")
                if debit > 0:
                    tx_type, amount = "expense", debit
                elif credit > 0:
                    tx_type, amount = "income", credit
                else:
                    raise ValueError("Debit/credit amount is empty.")
            else:
                signed = parse_signed_amount(raw_row.get(amount_col, ""))
                if tx_type is None:
                    if signed < 0:
                        tx_type = "expense" if positive_is == "income" else "income"
                    else:
                        tx_type = positive_is
                amount = abs(signed)
                if amount == 0:
                    raise ValueError("A zero amount cannot be imported.")
            if tx_type not in {"expense", "income"}:
                raise ValueError("Transaction type could not be determined.")
            if not description:
                raise ValueError("Description is empty.")

            if category_col and (raw_row.get(category_col) or "").strip():
                category = resolve_category(conn, raw_row[category_col], tx_type)
            else:
                category = infer_category(conn, description, tx_type)
            if category:
                category_id = category["id"]
                category_name = category["name"]
            else:
                status = "unresolved"
                error = "Category could not be determined."

            if external_col and (raw_row.get(external_col) or "").strip():
                external_id = f"{normalize(source_name)}:{raw_row[external_col].strip()}"
                if conn.execute(
                    "SELECT 1 FROM transactions WHERE external_id=?", (external_id,)
                ).fetchone():
                    status = "duplicate"
                    error = "External ID has already been imported."

            if status == "ready":
                duplicates = duplicate_candidates(
                    conn,
                    occurred_at=occurred_at,
                    tx_type=tx_type,
                    amount=amount,
                    wallet_id=wallet["id"],
                    category_id=category_id,
                    description=description,
                )
                if duplicates:
                    status = "duplicate"
                    error = f"Similar to transaction #{duplicates[0]['id']}."
        except Exception as exc:
            status = "error"
            error = str(exc)

        cursor = conn.execute(
            """
            INSERT INTO import_rows(
                batch_id,row_number,occurred_at,type,amount,description,category_id,
                external_id,raw_json,status,error_message
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                batch_id,
                index,
                occurred_at,
                tx_type,
                amount,
                description,
                category_id,
                external_id,
                json.dumps(raw_row, ensure_ascii=False),
                status,
                error,
            ),
        )
        counters[status] += 1
        preview_rows.append(
            {
                "import_row_id": cursor.lastrowid,
                "row_number": index,
                "status": status,
                "occurred_at": occurred_at,
                "type": tx_type,
                "amount": amount,
                "amount_formatted": rupiah(amount) if amount else None,
                "description": description,
                "category": category_name,
                "external_id": external_id,
                "error": error,
            }
        )

    conn.execute(
        """
        UPDATE import_batches
        SET total_rows=?,valid_rows=?,unresolved_rows=?,duplicate_rows=?
        WHERE id=?
        """,
        (
            len(rows),
            counters["ready"],
            counters["unresolved"] + counters["error"],
            counters["duplicate"],
            batch_id,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "batch_id": batch_id,
        "source": source_name,
        "wallet": wallet["name"],
        "columns": {
            "date": date_col,
            "description": desc_col,
            "amount": amount_col,
            "debit": debit_col,
            "credit": credit_col,
            "type": type_col,
            "external_id": external_col,
            "category": category_col,
        },
        "summary": {"total": len(rows), **counters},
        "rows": preview_rows,
        "committed": False,
    }


def import_rows_list(batch_id: int) -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        """
        SELECT ir.*,c.name AS category
        FROM import_rows ir LEFT JOIN categories c ON c.id=ir.category_id
        WHERE ir.batch_id=? ORDER BY ir.row_number
        """,
        (batch_id,),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["amount_formatted"] = rupiah(item["amount"]) if item["amount"] else None
        result.append(item)
    return result


def import_row_set(
    *,
    import_row_id: int,
    category_name: str | None = None,
    tx_type: str | None = None,
    skip: bool = False,
) -> dict[str, Any]:
    conn = connect()
    row = conn.execute("SELECT * FROM import_rows WHERE id=?", (import_row_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Import row #{import_row_id} not found.")
    if row["status"] == "committed":
        conn.close()
        raise ValueError("Row has already been committed.")
    if skip:
        conn.execute(
            "UPDATE import_rows SET status='skipped',error_message=NULL WHERE id=?",
            (import_row_id,),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "import_row_id": import_row_id, "status": "skipped"}

    final_type = tx_type or row["type"]
    if final_type not in {"expense", "income"}:
        conn.close()
        raise ValueError("Transaction type must be expense or income.")
    category_id = row["category_id"]
    category_label = None
    if category_name:
        category = resolve_category(conn, category_name, final_type)
        category_id = category["id"]
        category_label = category["name"]
    elif category_id:
        category = conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        if category and category["type"] != final_type:
            category_id = None
        else:
            category_label = category["name"] if category else None
    if not category_id:
        conn.close()
        raise ValueError("A category is required before the row can be committed.")
    conn.execute(
        """
        UPDATE import_rows
        SET type=?,category_id=?,status='ready',error_message=NULL
        WHERE id=?
        """,
        (final_type, category_id, import_row_id),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "import_row_id": import_row_id,
        "type": final_type,
        "category": category_label or category_name,
        "status": "ready",
    }


def import_commit(batch_id: int, force_duplicates: bool = False) -> dict[str, Any]:
    conn = connect()
    batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        raise ValueError(f"Import batch #{batch_id} not found.")
    if batch["status"] != "preview":
        conn.close()
        raise ValueError("This batch has already been committed or cancelled.")
    wallet = conn.execute("SELECT * FROM wallets WHERE id=?", (batch["wallet_id"],)).fetchone()
    statuses = ["ready"] + (["duplicate"] if force_duplicates else [])
    placeholders = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"""
        SELECT ir.*,c.name AS category_name
        FROM import_rows ir JOIN categories c ON c.id=ir.category_id
        WHERE ir.batch_id=? AND ir.status IN ({placeholders})
        ORDER BY ir.row_number
        """,
        (batch_id, *statuses),
    ).fetchall()
    committed = []
    failed = []
    for row in rows:
        try:
            if row["external_id"] and conn.execute(
                "SELECT 1 FROM transactions WHERE external_id=?", (row["external_id"],)
            ).fetchone():
                raise ValueError(f"External ID {row['external_id']!r} has already been imported.")
            duplicates = duplicate_candidates(
                conn,
                occurred_at=row["occurred_at"],
                tx_type=row["type"],
                amount=row["amount"],
                wallet_id=wallet["id"],
                category_id=row["category_id"],
                description=row["description"],
            )
            if duplicates and not force_duplicates:
                raise ValueError(f"Similar to transaction #{duplicates[0]['id']}; review before committing.")
            tx_id = create_transaction(
                conn,
                tx_type=row["type"],
                amount=row["amount"],
                wallet_id=wallet["id"],
                category_id=row["category_id"],
                description=row["description"],
                occurred_at=row["occurred_at"],
                source=f"csv:{batch['source_name']}",
                external_id=row["external_id"],
                import_batch_id=batch_id,
            )
            conn.execute(
                "UPDATE import_rows SET status='committed',transaction_id=?,error_message=NULL WHERE id=?",
                (tx_id, row["id"]),
            )
            committed.append({
                "ok": True,
                "transaction_id": tx_id,
                "import_row_id": row["id"],
                "type": row["type"],
                "amount": row["amount"],
                "amount_formatted": rupiah(row["amount"]),
                "category": row["category_name"],
                "wallet": wallet["name"],
                "description": row["description"],
                "occurred_at": row["occurred_at"],
                "external_id": row["external_id"],
            })
        except Exception as exc:
            failed.append({"import_row_id": row["id"], "error": str(exc)})
            conn.execute(
                "UPDATE import_rows SET error_message=? WHERE id=?",
                (str(exc), row["id"]),
            )
    remaining = conn.execute(
        "SELECT COUNT(*) AS count FROM import_rows WHERE batch_id=? AND status IN ('ready','unresolved','duplicate','error')",
        (batch_id,),
    ).fetchone()["count"]
    status = "committed" if remaining == 0 else "preview"
    conn.execute(
        "UPDATE import_batches SET status=?,committed_at=? WHERE id=?",
        (
            status,
            datetime.now(TZ).isoformat(timespec="seconds") if status == "committed" else None,
            batch_id,
        ),
    )
    conn.commit()
    balance = wallet_balance(conn, wallet["id"])
    conn.close()
    return {
        "ok": len(failed) == 0,
        "batch_id": batch_id,
        "committed_count": len(committed),
        "failed_count": len(failed),
        "remaining_review_count": remaining,
        "wallet": wallet["name"],
        "wallet_balance": balance,
        "wallet_balance_formatted": rupiah(balance),
        "transactions": committed,
        "failures": failed,
    }


def export_csv(output_path: str) -> str:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    rows = conn.execute(
        """
        SELECT t.id,t.occurred_at,t.type,t.amount,c.name AS category,
               w.name AS wallet,tw.name AS to_wallet,t.description,t.note,
               t.source,t.status,t.external_id,t.created_at,t.voided_at,t.void_reason
        FROM transactions t
        LEFT JOIN categories c ON c.id=t.category_id
        JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN wallets tw ON tw.id=t.to_wallet_id
        ORDER BY t.occurred_at,t.id
        """
    ).fetchall()
    conn.close()
    fields = [
        "id", "occurred_at", "type", "amount", "category", "wallet", "to_wallet",
        "description", "note", "source", "status", "external_id", "created_at",
        "voided_at", "void_reason",
    ]
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    return str(output)
