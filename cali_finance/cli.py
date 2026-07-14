from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .alerts import alert_data, alert_text
from .backup import backup_local, backup_offsite, last_backup, restore_backup
from .budgets import budget_cancel, budget_set, budget_status
from .config import DB_PATH
from .dashboard import dashboard_generate
from .db import db_integrity, init_db
from .goals import goal_add, goal_contribute, goal_withdraw, goals_list
from .imports import export_csv, import_commit, import_preview, import_row_set, import_rows_list
from .ledger import (
    add_transaction,
    all_wallet_balances,
    categories,
    category_add,
    recent_transactions,
    reconcile_adjust,
    reconcile_close,
    reconcile_preview,
    search_transactions,
    transfer,
    void_transaction,
    wallet_add,
    wallet_set,
)
from .db import connect
from .obligations import (
    obligation_add,
    obligation_cancel,
    obligation_pay,
    obligations_list,
    recurring_add,
    recurring_list,
    recurring_pause,
    recurring_run,
)
from .receipts import receipt_confirm, receipt_reject, receipt_scan, receipts_list
from .reports import report_data, report_text, safe_to_spend
from .settings import all_settings, set_setting


def emit(value, *, pretty: bool = False) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None))


def _wallets(_args):
    conn = connect()
    result = all_wallet_balances(conn)
    conn.close()
    return result


def _init(_args):
    init_db()
    return {"ok": True, "version": __version__, "database": str(DB_PATH)}


def _health(_args):
    integrity = db_integrity()
    conn = connect()
    wallets = all_wallet_balances(conn)
    conn.close()
    negative = [w for w in wallets if w["balance"] < 0]
    backup = last_backup()
    return {
        "ok": integrity["integrity"] == "ok" and not integrity["foreign_key_errors"],
        "version": __version__,
        "integrity": integrity,
        "negative_wallets": negative,
        "last_backup": backup,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finance.py",
        description="Cali — local-first personal finance ledger for Hermes Agent.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Initialize or migrate the database.")
    p.set_defaults(func=_init)

    p = sub.add_parser("health", help="Check database integrity and basic health.")
    p.set_defaults(func=_health)

    p = sub.add_parser("add", help="Record expense or income.")
    p.add_argument("--type", required=True, choices=["expense", "income"])
    p.add_argument("--amount", required=True)
    p.add_argument("--category")
    p.add_argument("--wallet", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--raw-input")
    p.add_argument("--source", default="hermes")
    p.add_argument("--force-duplicate", action="store_true")
    p.set_defaults(
        func=lambda a: add_transaction(
            tx_type=a.type,
            amount_raw=a.amount,
            wallet_name=a.wallet,
            description=a.description,
            category_name=a.category,
            date_raw=a.date,
            note=a.note,
            raw_input=a.raw_input,
            source=a.source,
            force_duplicate=a.force_duplicate,
        )
    )

    p = sub.add_parser("transfer", help="Transfer money between wallets.")
    p.add_argument("--amount", required=True)
    p.add_argument("--from-wallet", required=True)
    p.add_argument("--to-wallet", required=True)
    p.add_argument("--description", default="Transfer between wallets")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--raw-input")
    p.set_defaults(
        func=lambda a: transfer(
            amount_raw=a.amount,
            from_wallet_name=a.from_wallet,
            to_wallet_name=a.to_wallet,
            description=a.description,
            date_raw=a.date,
            note=a.note,
            raw_input=a.raw_input,
        )
    )

    p = sub.add_parser("wallet-add")
    p.add_argument("--name", required=True)
    p.add_argument("--kind", default="other", choices=["cash", "bank", "ewallet", "other"])
    p.add_argument("--opening-balance", default="0")
    p.add_argument("--aliases")
    p.set_defaults(func=lambda a: wallet_add(a.name, a.kind, a.opening_balance, a.aliases))

    p = sub.add_parser("wallet-set")
    p.add_argument("--name", required=True)
    p.add_argument("--kind", choices=["cash", "bank", "ewallet", "other"])
    p.add_argument("--opening-balance")
    p.add_argument("--aliases")
    p.set_defaults(func=lambda a: wallet_set(a.name, a.kind, a.opening_balance, a.aliases))

    p = sub.add_parser("wallets")
    p.set_defaults(func=_wallets)

    p = sub.add_parser("category-add")
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True, choices=["expense", "income"])
    p.add_argument("--aliases")
    p.set_defaults(func=lambda a: category_add(a.name, a.type, a.aliases))

    p = sub.add_parser("categories")
    p.add_argument("--type", choices=["expense", "income"])
    p.set_defaults(func=lambda a: categories(a.type))

    p = sub.add_parser("list", help="List recent transactions.")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=lambda a: recent_transactions(a.limit))

    p = sub.add_parser("search", help="Search transactions with validated filters.")
    p.add_argument("--query")
    p.add_argument("--from", dest="date_from")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--min-amount")
    p.add_argument("--max-amount")
    p.add_argument("--category")
    p.add_argument("--wallet")
    p.add_argument("--type")
    p.add_argument("--status", default="active", choices=["active", "void"])
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(
        func=lambda a: search_transactions(
            query=a.query,
            date_from=a.date_from,
            date_to=a.date_to,
            min_amount=a.min_amount,
            max_amount=a.max_amount,
            category_name=a.category,
            wallet_name=a.wallet,
            tx_type=a.type,
            status=a.status,
            limit=a.limit,
        )
    )

    p = sub.add_parser("void")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=lambda a: void_transaction(a.id, a.reason))

    p = sub.add_parser("reconcile", help="Preview difference between actual and recorded balance.")
    p.add_argument("--wallet", required=True)
    p.add_argument("--actual-balance", required=True)
    p.add_argument("--note")
    p.set_defaults(func=lambda a: reconcile_preview(a.wallet, a.actual_balance, a.note))

    p = sub.add_parser("reconcile-adjust")
    p.add_argument("--check-id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--confirm-adjust", required=True)
    p.set_defaults(func=lambda a: reconcile_adjust(a.check_id, a.reason, a.confirm_adjust))

    p = sub.add_parser("reconcile-close")
    p.add_argument("--check-id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=lambda a: reconcile_close(a.check_id, a.reason))

    p = sub.add_parser("budget-set")
    p.add_argument("--limit", required=True)
    p.add_argument("--category")
    p.add_argument("--period", default="month", choices=["month", "week"])
    p.add_argument("--start-date")
    p.set_defaults(
        func=lambda a: budget_set(
            limit_raw=a.limit,
            category_name=a.category,
            period_type=a.period,
            start_date=a.start_date,
        )
    )

    p = sub.add_parser("budgets")
    p.add_argument("--date")
    p.add_argument("--period", choices=["month", "week"])
    p.add_argument("--category")
    p.set_defaults(
        func=lambda a: budget_status(
            anchor_date=a.date,
            period_type=a.period,
            category_name=a.category,
        )
    )

    p = sub.add_parser("budget-cancel")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=lambda a: budget_cancel(a.id))

    p = sub.add_parser("bill-add")
    p.add_argument("--name", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--due-date")
    p.add_argument("--category", required=True)
    p.add_argument("--wallet")
    p.add_argument("--counterparty")
    p.add_argument("--note")
    p.add_argument("--raw-input")
    p.set_defaults(
        func=lambda a: obligation_add(
            kind="bill",
            name=a.name,
            amount_raw=a.amount,
            due_date=a.due_date,
            counterparty=a.counterparty,
            category_name=a.category,
            default_wallet=a.wallet,
            note=a.note,
            raw_input=a.raw_input,
        )
    )

    p = sub.add_parser("debt-add", help="Record payable or receivable debt.")
    p.add_argument("--direction", required=True, choices=["payable", "receivable"])
    p.add_argument("--name", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--counterparty")
    p.add_argument("--due-date")
    p.add_argument("--wallet", help="Default payment/collection wallet.")
    p.add_argument("--cash-wallet", help="Record initial loan cash movement in this wallet.")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--raw-input")
    p.set_defaults(
        func=lambda a: obligation_add(
            kind="debt_payable" if a.direction == "payable" else "debt_receivable",
            name=a.name,
            amount_raw=a.amount,
            due_date=a.due_date,
            counterparty=a.counterparty,
            default_wallet=a.wallet,
            note=a.note,
            raw_input=a.raw_input,
            cash_wallet=a.cash_wallet,
            date_raw=a.date,
        )
    )

    p = sub.add_parser("obligation-pay", help="Pay a bill/debt or collect receivable.")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--wallet", required=True)
    p.add_argument("--date")
    p.add_argument("--note")
    p.set_defaults(
        func=lambda a: obligation_pay(
            obligation_id=a.id,
            amount_raw=a.amount,
            wallet_name=a.wallet,
            date_raw=a.date,
            note=a.note,
        )
    )

    p = sub.add_parser("obligations")
    p.add_argument("--kind", choices=["bill", "debt_payable", "debt_receivable"])
    p.add_argument("--status", choices=["open", "partial", "paid", "overdue", "cancelled"])
    p.add_argument("--due-before")
    p.set_defaults(func=lambda a: obligations_list(kind=a.kind, status=a.status, due_before=a.due_before))

    p = sub.add_parser("obligation-cancel")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=lambda a: obligation_cancel(a.id, a.reason))

    p = sub.add_parser("recurring-add")
    p.add_argument("--name", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--next-due-date", required=True)
    p.add_argument("--frequency", default="monthly", choices=["weekly", "monthly", "yearly"])
    p.add_argument("--interval", type=int, default=1)
    p.add_argument("--wallet")
    p.add_argument("--note")
    p.set_defaults(
        func=lambda a: recurring_add(
            name=a.name,
            amount_raw=a.amount,
            category_name=a.category,
            next_due_date=a.next_due_date,
            frequency=a.frequency,
            interval_count=a.interval,
            default_wallet=a.wallet,
            note=a.note,
        )
    )

    p = sub.add_parser("recurring-run")
    p.add_argument("--until")
    p.set_defaults(func=lambda a: recurring_run(a.until))

    p = sub.add_parser("recurring-list")
    p.set_defaults(func=lambda a: recurring_list())

    p = sub.add_parser("recurring-pause")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=lambda a: recurring_pause(a.id, False))

    p = sub.add_parser("recurring-resume")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=lambda a: recurring_pause(a.id, True))

    p = sub.add_parser("goal-add")
    p.add_argument("--name", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--target-date")
    p.add_argument("--linked-wallet")
    p.add_argument("--note")
    p.set_defaults(
        func=lambda a: goal_add(
            name=a.name,
            target_raw=a.target,
            target_date=a.target_date,
            linked_wallet=a.linked_wallet,
            note=a.note,
        )
    )

    p = sub.add_parser("goal-contribute")
    p.add_argument("--goal", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--wallet")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--force-over-target", action="store_true")
    p.set_defaults(
        func=lambda a: goal_contribute(
            goal=a.goal,
            amount_raw=a.amount,
            wallet_name=a.wallet,
            date_raw=a.date,
            note=a.note,
            force_over_target=a.force_over_target,
        )
    )

    p = sub.add_parser("goal-withdraw")
    p.add_argument("--goal", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--date")
    p.add_argument("--note")
    p.set_defaults(
        func=lambda a: goal_withdraw(
            goal=a.goal,
            amount_raw=a.amount,
            date_raw=a.date,
            note=a.note,
        )
    )

    p = sub.add_parser("goals")
    p.add_argument("--status", choices=["active", "completed", "paused", "cancelled"])
    p.set_defaults(func=lambda a: goals_list(a.status))

    p = sub.add_parser("report")
    p.add_argument("--period", required=True, choices=["week", "month"])
    p.add_argument("--date")
    p.add_argument("--format", default="text", choices=["text", "json"])
    p.set_defaults(
        func=lambda a: report_text(report_data(a.period, a.date)) if a.format == "text" else report_data(a.period, a.date)
    )

    p = sub.add_parser("safe-to-spend")
    p.add_argument("--date")
    p.set_defaults(func=lambda a: safe_to_spend(a.date))

    p = sub.add_parser("config-set")
    p.add_argument("--key", required=True)
    p.add_argument("--value", required=True)
    p.set_defaults(func=lambda a: set_setting(a.key, a.value))

    p = sub.add_parser("config")
    p.set_defaults(func=lambda a: all_settings())

    p = sub.add_parser("import-preview")
    p.add_argument("--file", required=True)
    p.add_argument("--wallet", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--date-column")
    p.add_argument("--description-column")
    p.add_argument("--amount-column")
    p.add_argument("--debit-column")
    p.add_argument("--credit-column")
    p.add_argument("--type-column")
    p.add_argument("--external-id-column")
    p.add_argument("--category-column")
    p.add_argument("--date-format")
    p.add_argument("--positive-is", default="income", choices=["income", "expense"])
    p.set_defaults(
        func=lambda a: import_preview(
            file_path=a.file,
            wallet_name=a.wallet,
            source_name=a.source,
            date_column=a.date_column,
            description_column=a.description_column,
            amount_column=a.amount_column,
            debit_column=a.debit_column,
            credit_column=a.credit_column,
            type_column=a.type_column,
            external_id_column=a.external_id_column,
            category_column=a.category_column,
            date_format=a.date_format,
            positive_is=a.positive_is,
        )
    )

    p = sub.add_parser("import-rows")
    p.add_argument("--batch-id", type=int, required=True)
    p.set_defaults(func=lambda a: import_rows_list(a.batch_id))

    p = sub.add_parser("import-row-set")
    p.add_argument("--row-id", type=int, required=True)
    p.add_argument("--category")
    p.add_argument("--type", choices=["expense", "income"])
    p.add_argument("--skip", action="store_true")
    p.set_defaults(
        func=lambda a: import_row_set(
            import_row_id=a.row_id,
            category_name=a.category,
            tx_type=a.type,
            skip=a.skip,
        )
    )

    p = sub.add_parser("import-commit")
    p.add_argument("--batch-id", type=int, required=True)
    p.add_argument("--force-duplicates", action="store_true")
    p.set_defaults(func=lambda a: import_commit(a.batch_id, a.force_duplicates))

    p = sub.add_parser("export-csv")
    p.add_argument("--output", required=True)
    p.set_defaults(func=lambda a: {"ok": True, "output": export_csv(a.output)})

    p = sub.add_parser("receipt-scan")
    p.add_argument("--file", required=True)
    p.add_argument("--wallet")
    p.add_argument("--ocr", action="store_true")
    p.set_defaults(func=lambda a: receipt_scan(file_path=a.file, wallet_name=a.wallet, run_ocr=a.ocr))

    p = sub.add_parser("receipt-confirm")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--wallet", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--amount")
    p.add_argument("--date")
    p.add_argument("--merchant")
    p.add_argument("--force-duplicate", action="store_true")
    p.set_defaults(
        func=lambda a: receipt_confirm(
            receipt_id=a.id,
            wallet_name=a.wallet,
            category_name=a.category,
            description=a.description,
            amount_raw=a.amount,
            date_raw=a.date,
            merchant=a.merchant,
            force_duplicate=a.force_duplicate,
        )
    )

    p = sub.add_parser("receipt-reject")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=lambda a: receipt_reject(a.id, a.reason))

    p = sub.add_parser("receipts")
    p.add_argument("--status", choices=["preview", "committed", "rejected"])
    p.set_defaults(func=lambda a: receipts_list(a.status))

    p = sub.add_parser("dashboard-generate")
    p.add_argument("--output")
    p.add_argument("--period", default="month", choices=["week", "month"])
    p.add_argument("--date")
    p.set_defaults(
        func=lambda a: {
            "ok": True,
            "output": dashboard_generate(output_path=a.output, period=a.period, anchor_date=a.date),
        }
    )

    p = sub.add_parser("alerts")
    p.add_argument("--new-only", action="store_true")
    p.add_argument("--mark-sent", action="store_true")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(
        func=lambda a: (
            alert_text(alert_data(new_only=a.new_only, mark_sent=a.mark_sent))
            if a.format == "text"
            else alert_data(new_only=a.new_only, mark_sent=a.mark_sent)
        )
    )

    p = sub.add_parser("backup")
    p.add_argument("--keep", type=int, default=30)
    p.add_argument("--offsite", action="store_true")
    p.set_defaults(func=lambda a: backup_offsite(a.keep) if a.offsite else backup_local(a.keep))

    p = sub.add_parser("restore", help="Restore a backup archive. Stop the gateway first.")
    p.add_argument("--archive", required=True)
    p.add_argument("--confirm", required=True)
    p.set_defaults(func=lambda a: restore_backup(a.archive, a.confirm))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        if result == "":
            return 0
        emit(result, pretty=args.pretty)
        if isinstance(result, dict) and result.get("ok") is False:
            return 2
        return 0
    except (ValueError, OSError) as exc:
        emit({"ok": False, "error": str(exc)}, pretty=args.pretty)
        return 1
    except Exception as exc:
        emit({"ok": False, "error": f"Unexpected error: {exc.__class__.__name__}: {exc}"}, pretty=args.pretty)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
