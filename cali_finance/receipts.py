from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RECEIPT_DIR, TZ
from .db import connect
from .ledger import add_transaction, infer_category, parse_occurrence, resolve_category, resolve_wallet
from .money import parse_amount, rupiah


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_tesseract(path: Path) -> str:
    binary = shutil.which("tesseract")
    if not binary:
        raise ValueError(
            "Tesseract is not installed. Run install-ocr.sh or enter the receipt data manually."
        )
    languages = "ind+eng"
    result = subprocess.run(
        [binary, str(path), "stdout", "-l", languages],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        # Some minimal installations only ship English.
        result = subprocess.run(
            [binary, str(path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    if result.returncode != 0:
        raise ValueError(f"OCR failed: {result.stderr.strip() or 'unknown error'}")
    return result.stdout.strip()


def _parse_receipt_text(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = None
    for line in lines[:8]:
        if len(line) >= 3 and not re.fullmatch(r"[\d\W_]+", line):
            merchant = line[:120]
            break

    occurred_at = None
    date_patterns = [
        r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b",
        r"\b(\d{4})[/-](\d{2})[/-](\d{2})\b",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            parts = match.groups()
            try:
                if len(parts[0]) == 4:
                    candidate = f"{parts[0]}-{parts[1]}-{parts[2]}"
                else:
                    candidate = f"{parts[2]}-{parts[1]}-{parts[0]}"
                occurred_at = parse_occurrence(candidate)
                break
            except ValueError:
                continue

    total_amount = None
    prioritized = []
    generic = []
    for line in lines:
        numbers = re.findall(r"(?:rp\s*)?([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]{4,})", line, flags=re.I)
        for number in numbers:
            try:
                amount = parse_amount(number)
            except ValueError:
                continue
            if re.search(r"grand\s*total|total\s*(bayar|payment)?|jumlah\s*bayar", line, flags=re.I):
                prioritized.append(amount)
            else:
                generic.append(amount)
    if prioritized:
        total_amount = max(prioritized)
    elif generic:
        total_amount = max(generic)

    return {
        "merchant": merchant,
        "occurred_at": occurred_at,
        "total_amount": total_amount,
    }


def receipt_scan(
    *,
    file_path: str,
    wallet_name: str | None = None,
    run_ocr: bool = False,
) -> dict[str, Any]:
    source = Path(file_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise ValueError(f"Receipt file not found: {source}")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        raise ValueError("Receipt format must be PNG, JPG, WEBP, or TIFF.")

    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    digest = _sha256(source)
    conn = connect()
    existing = conn.execute("SELECT * FROM receipts WHERE sha256=?", (digest,)).fetchone()
    if existing:
        conn.close()
        raise ValueError(f"The same receipt was already processed as receipt #{existing['id']}.")

    destination = RECEIPT_DIR / f"{digest[:16]}{source.suffix.lower()}"
    shutil.copy2(source, destination)
    ocr_text = _run_tesseract(destination) if run_ocr else None
    parsed = _parse_receipt_text(ocr_text or "")

    wallet_id = None
    wallet_label = None
    if wallet_name:
        wallet = resolve_wallet(conn, wallet_name)
        wallet_id = wallet["id"]
        wallet_label = wallet["name"]

    category_id = None
    category_label = None
    if ocr_text:
        category = infer_category(conn, ocr_text, "expense")
        if category:
            category_id = category["id"]
            category_label = category["name"]

    now = datetime.now(TZ).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO receipts(
            image_path,sha256,merchant,occurred_at,total_amount,category_id,wallet_id,
            ocr_text,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,'preview',?)
        """,
        (
            str(destination),
            digest,
            parsed["merchant"],
            parsed["occurred_at"],
            parsed["total_amount"],
            category_id,
            wallet_id,
            ocr_text,
            now,
        ),
    )
    receipt_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "receipt_id": receipt_id,
        "image_path": str(destination),
        "merchant": parsed["merchant"],
        "occurred_at": parsed["occurred_at"],
        "total_amount": parsed["total_amount"],
        "total_amount_formatted": rupiah(parsed["total_amount"]) if parsed["total_amount"] else None,
        "category": category_label,
        "wallet": wallet_label,
        "ocr_used": run_ocr,
        "ocr_text_preview": (ocr_text[:1000] if ocr_text else None),
        "status": "preview",
        "requires_confirmation": True,
    }


def receipt_confirm(
    *,
    receipt_id: int,
    wallet_name: str,
    category_name: str,
    description: str,
    amount_raw: str | int | None = None,
    date_raw: str | None = None,
    merchant: str | None = None,
    force_duplicate: bool = False,
) -> dict[str, Any]:
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        receipt = conn.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
        if not receipt:
            raise ValueError(f"Receipt #{receipt_id} not found.")
        if receipt["status"] != "preview":
            raise ValueError("This receipt has already been committed or rejected.")
        amount = amount_raw if amount_raw is not None else receipt["total_amount"]
        if amount is None:
            raise ValueError("Amount could not be read. Specify --amount.")

        result = add_transaction(
            tx_type="expense",
            amount_raw=amount,
            wallet_name=wallet_name,
            description=description,
            category_name=category_name,
            date_raw=date_raw or receipt["occurred_at"],
            note=f"Receipt #{receipt_id}; merchant={merchant or receipt['merchant'] or '-'}",
            source="receipt",
            force_duplicate=force_duplicate,
            receipt_id=receipt_id,
            _conn=conn,
        )
        if not result["ok"]:
            conn.rollback()
            return result
        conn.execute(
            """
            UPDATE receipts
            SET status='committed',transaction_id=?,merchant=COALESCE(?,merchant),
                total_amount=?,occurred_at=?,
                category_id=(SELECT id FROM categories WHERE name=? COLLATE NOCASE),
                wallet_id=(SELECT id FROM wallets WHERE name=? COLLATE NOCASE)
            WHERE id=?
            """,
            (
                result["transaction_id"],
                merchant,
                result["amount"],
                result["occurred_at"],
                result["category"],
                result["wallet"],
                receipt_id,
            ),
        )
        conn.commit()
        result["receipt_id"] = receipt_id
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def receipt_reject(receipt_id: int, reason: str) -> dict[str, Any]:
    conn = connect()
    cursor = conn.execute(
        "UPDATE receipts SET status='rejected',ocr_text=COALESCE(ocr_text,'') || ? WHERE id=? AND status='preview'",
        (f"\n[Rejected: {reason.strip()}]", receipt_id),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise ValueError("Receipt not found or already processed.")
    conn.commit()
    conn.close()
    return {"ok": True, "receipt_id": receipt_id, "status": "rejected"}


def receipts_list(status: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    if status:
        rows = conn.execute(
            """
            SELECT r.*,c.name AS category,w.name AS wallet
            FROM receipts r
            LEFT JOIN categories c ON c.id=r.category_id
            LEFT JOIN wallets w ON w.id=r.wallet_id
            WHERE r.status=? ORDER BY r.created_at DESC
            """,
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.*,c.name AS category,w.name AS wallet
            FROM receipts r
            LEFT JOIN categories c ON c.id=r.category_id
            LEFT JOIN wallets w ON w.id=r.wallet_id
            ORDER BY r.created_at DESC
            """
        ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["total_amount_formatted"] = rupiah(item["total_amount"]) if item["total_amount"] else None
        if item.get("ocr_text"):
            item["ocr_text"] = item["ocr_text"][:500]
        result.append(item)
    return result
