#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(tempfile.mkdtemp(prefix="cali-finance-test-"))
os.environ["HERMES_HOME"] = str(ROOT / ".hermes")

from cali_finance.alerts import alert_data
from cali_finance.backup import backup_local
from cali_finance.budgets import budget_set
from cali_finance.config import TZ
from cali_finance.dashboard import dashboard_generate
from cali_finance.db import connect, db_integrity, init_db
from cali_finance.goals import goal_add, goal_contribute
from cali_finance.imports import import_commit, import_preview
from cali_finance.ledger import (
    add_transaction,
    reconcile_adjust,
    reconcile_preview,
    transfer,
    void_transaction,
    wallet_add,
    wallet_balance,
    wallet_set,
)
from cali_finance.obligations import (
    obligation_add,
    obligation_pay,
    recurring_add,
    recurring_run,
)
from cali_finance.receipts import receipt_confirm, receipt_scan
from cali_finance.reports import report_data, safe_to_spend
from cali_finance.settings import set_setting


def main() -> None:
    today = datetime.now(TZ).date()
    month_start = today.replace(day=1)
    tomorrow = today + timedelta(days=1)

    init_db()
    wallet_set("Cash", opening_balance_raw="500000")
    wallet_set("GoPay", opening_balance_raw="200000")
    wallet_add("BCA", "bank", "1000000", "rekening bca,bca mobile")

    first = add_transaction(
        tx_type="expense",
        amount_raw="25000",
        wallet_name="Cash",
        description="Meatball soup",
        category_name="Food",
        date_raw=today.isoformat(),
    )
    assert first["ok"]

    duplicate = add_transaction(
        tx_type="expense",
        amount_raw="25000",
        wallet_name="Cash",
        description="Meatball soup",
        category_name="Food",
        date_raw=today.isoformat(),
    )
    assert duplicate["code"] == "possible_duplicate"

    add_transaction(
        tx_type="expense",
        amount_raw="25000",
        wallet_name="Cash",
        description="Meatball soup",
        category_name="Food",
        date_raw=today.isoformat(),
        force_duplicate=True,
    )
    transfer(
        amount_raw="100000",
        from_wallet_name="BCA",
        to_wallet_name="GoPay",
        description="Top up GoPay",
    )

    budget_set(
        limit_raw="60000",
        category_name="Food",
        period_type="month",
        start_date=month_start.isoformat(),
    )
    budget_hit = add_transaction(
        tx_type="expense",
        amount_raw="10000",
        wallet_name="Cash",
        description="Buy coffee",
        category_name="Food",
        date_raw=today.isoformat(),
    )
    assert budget_hit["budget_warnings"][0]["threshold"] == 100

    obligation_add(
        kind="bill",
        name="Internet",
        amount_raw="275000",
        due_date=tomorrow.isoformat(),
        category_name="Bills",
        default_wallet="BCA",
    )
    obligation_add(
        kind="debt_payable",
        name="Loan from Umar",
        amount_raw="500000",
        counterparty="Umar",
        due_date=(today + timedelta(days=30)).isoformat(),
        cash_wallet="BCA",
    )
    obligation_add(
        kind="debt_receivable",
        name="Loan to Zaki",
        amount_raw="200000",
        counterparty="Zaki",
        due_date=(today + timedelta(days=20)).isoformat(),
        cash_wallet="Cash",
    )
    obligation_pay(obligation_id=1, amount_raw="275000", wallet_name="BCA")
    obligation_pay(obligation_id=2, amount_raw="100000", wallet_name="BCA")
    obligation_pay(obligation_id=3, amount_raw="50000", wallet_name="Cash")

    voidable = obligation_add(
        kind="bill",
        name="Void regression",
        amount_raw="120000",
        due_date=tomorrow.isoformat(),
        category_name="Bills",
    )
    voided_payment = obligation_pay(
        obligation_id=voidable["obligation_id"],
        amount_raw="120000",
        wallet_name="BCA",
    )
    void_transaction(voided_payment["transaction_id"], "Regression test")
    conn = connect()
    restored = conn.execute(
        "SELECT remaining_amount,status,closed_at FROM obligations WHERE id=?",
        (voidable["obligation_id"],),
    ).fetchone()
    bca_id = conn.execute("SELECT id FROM wallets WHERE name='BCA'").fetchone()["id"]
    assert dict(restored) == {
        "remaining_amount": 120000,
        "status": "open",
        "closed_at": None,
    }
    assert wallet_balance(conn, bca_id) == voided_payment["wallet_balance"] + 120000
    conn.close()

    recurring_add(
        name="Netflix",
        amount_raw="65000",
        category_name="Subscriptions",
        next_due_date=today.isoformat(),
        default_wallet="GoPay",
    )
    assert recurring_run((today + timedelta(days=35)).isoformat())["created_count"] >= 1

    goal_add(name="Laptop", target_raw="10000000", linked_wallet="BCA")
    goal_contribute(
        goal="Laptop",
        amount_raw="500000",
        wallet_name="BCA",
        date_raw=today.isoformat(),
    )
    set_setting("minimum_reserve", "400000")
    set_setting("monthly_savings_target", "500000")
    assert "safe_to_spend" in safe_to_spend(today.isoformat())

    report = report_data("month", today.isoformat())
    assert report["current"]["expense_total"] >= 335000
    assert "category_changes" in report["comparison"]

    wallet_add("Reconciliation", "cash", "100000", None)
    check = reconcile_preview("Reconciliation", "120000")
    add_transaction(
        tx_type="expense",
        amount_raw="10000",
        wallet_name="Reconciliation",
        description="Expense recorded after reconciliation preview",
        category_name="Food",
    )
    adjustment = reconcile_adjust(check["check_id"], "Test difference", "YES")
    assert adjustment["adjustment"] == 30000
    assert adjustment["new_balance"] == 120000

    csv_path = ROOT / "bank.csv"
    csv_path.write_text(
        "date,description,debit,credit,reference\n"
        f"{today.strftime('%d/%m/%Y')},GOJEK TRIP,20000,,a\n"
        f"{today.strftime('%d/%m/%Y')},Freelance income,,750000,b\n",
        encoding="utf-8",
    )
    batch = import_preview(
        file_path=str(csv_path),
        wallet_name="BCA",
        source_name="bank-test",
        date_format="%d/%m/%Y",
    )
    committed = import_commit(batch["batch_id"])
    assert committed["committed_count"] == 2

    receipt_path = ROOT / "receipt.png"
    receipt_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZJ9sAAAAASUVORK5CYII="
        )
    )
    receipt = receipt_scan(file_path=str(receipt_path), wallet_name="GoPay")
    conn = connect()
    conn.execute(
        f"""
        CREATE TRIGGER fail_receipt_commit
        BEFORE UPDATE OF status ON receipts
        WHEN NEW.id={receipt['receipt_id']} AND NEW.status='committed'
        BEGIN SELECT RAISE(ABORT, 'forced receipt update failure'); END
        """
    )
    conn.commit()
    conn.close()
    try:
        receipt_confirm(
            receipt_id=receipt["receipt_id"],
            wallet_name="GoPay",
            category_name="Food",
            description="Coffee from receipt",
            amount_raw="18000",
            date_raw=today.isoformat(),
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("Receipt confirmation failure did not roll back")
    conn = connect()
    assert conn.execute(
        "SELECT status FROM receipts WHERE id=?", (receipt["receipt_id"],)
    ).fetchone()["status"] == "preview"
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE receipt_id=?",
        (receipt["receipt_id"],),
    ).fetchone()["count"] == 0
    conn.execute("DROP TRIGGER fail_receipt_commit")
    conn.commit()
    conn.close()
    receipt_confirm(
        receipt_id=receipt["receipt_id"],
        wallet_name="GoPay",
        category_name="Food",
        description="Coffee from receipt",
        amount_raw="18000",
        date_raw=today.isoformat(),
    )

    backup = backup_local()
    assert Path(backup["path"]).exists()
    dashboard = dashboard_generate(anchor_date=today.isoformat())
    assert Path(dashboard).exists()
    assert "alerts" in alert_data()
    assert db_integrity()["integrity"] == "ok"
    print(f"SMOKE_OK {ROOT}")


if __name__ == "__main__":
    main()
