from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from .budgets import budget_status
from .config import TZ
from .db import connect
from .goals import goals_list, total_allocated_active
from .ledger import all_wallet_balances
from .money import percent, rupiah
from .obligations import obligations_list, refresh_obligation_statuses
from .settings import get_setting


def period_bounds(period: str, anchor: date) -> tuple[date, date, str]:
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        label = f"{start.isoformat()} to {(end - timedelta(days=1)).isoformat()}"
    elif period == "month":
        start = anchor.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        label = start.strftime("%Y-%m")
    else:
        raise ValueError("Period must be week or month.")
    return start, end, label


def previous_bounds(period: str, start: date) -> tuple[date, date]:
    if period == "week":
        prev_end = start
        return start - timedelta(days=7), prev_end
    prev_anchor = start - timedelta(days=1)
    prev_start = prev_anchor.replace(day=1)
    return prev_start, start


def _rows_between(conn, start: date, end: date):
    start_dt = datetime.combine(start, time.min, TZ).isoformat(timespec="seconds")
    end_dt = datetime.combine(end, time.min, TZ).isoformat(timespec="seconds")
    return conn.execute(
        """
        SELECT t.id,t.occurred_at,t.type,t.amount,t.description,
               c.name AS category,w.name AS wallet,tw.name AS to_wallet
        FROM transactions t
        LEFT JOIN categories c ON c.id=t.category_id
        JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN wallets tw ON tw.id=t.to_wallet_id
        WHERE t.status='active' AND t.occurred_at>=? AND t.occurred_at<?
        ORDER BY t.occurred_at,t.id
        """,
        (start_dt, end_dt),
    ).fetchall()


def _summarize_rows(rows) -> dict[str, Any]:
    totals = defaultdict(int)
    by_category = defaultdict(int)
    by_wallet = defaultdict(int)
    top_expenses = []
    for row in rows:
        totals[row["type"]] += row["amount"]
        if row["type"] == "expense":
            by_category[row["category"] or "Uncategorized"] += row["amount"]
            by_wallet[row["wallet"]] += row["amount"]
            top_expenses.append(
                {
                    "id": row["id"],
                    "occurred_at": row["occurred_at"],
                    "amount": row["amount"],
                    "amount_formatted": rupiah(row["amount"]),
                    "description": row["description"],
                    "category": row["category"],
                    "wallet": row["wallet"],
                }
            )
    top_expenses.sort(key=lambda item: item["amount"], reverse=True)
    expense = totals["expense"]
    income = totals["income"]
    adjustments = totals["adjustment_in"] - totals["adjustment_out"]
    cash_movement = (
        income
        - expense
        + totals["debt_draw"]
        - totals["debt_repayment"]
        - totals["loan_given"]
        + totals["loan_collection"]
        + adjustments
    )
    return {
        "transaction_count": len(rows),
        "expense_total": expense,
        "income_total": income,
        "operating_net": income - expense,
        "debt_borrowed": totals["debt_draw"],
        "debt_repaid": totals["debt_repayment"],
        "loans_given": totals["loan_given"],
        "loans_collected": totals["loan_collection"],
        "adjustments_net": adjustments,
        "cash_movement": cash_movement,
        "expense_by_category": [
            {"name": name, "amount": amount, "amount_formatted": rupiah(amount)}
            for name, amount in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        ],
        "expense_by_wallet": [
            {"name": name, "amount": amount, "amount_formatted": rupiah(amount)}
            for name, amount in sorted(by_wallet.items(), key=lambda x: x[1], reverse=True)
        ],
        "top_expenses": top_expenses[:10],
    }



def _wallets_snapshot() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return all_wallet_balances(conn)
    finally:
        conn.close()

def report_data(period: str, anchor_date: str | None = None) -> dict[str, Any]:
    anchor = date.fromisoformat(anchor_date) if anchor_date else datetime.now(TZ).date()
    start, end, label = period_bounds(period, anchor)
    prev_start, prev_end = previous_bounds(period, start)
    conn = connect()
    refresh_obligation_statuses(conn)
    conn.commit()
    current = _summarize_rows(_rows_between(conn, start, end))
    previous = _summarize_rows(_rows_between(conn, prev_start, prev_end))
    conn.close()

    expense_change = current["expense_total"] - previous["expense_total"]
    current_categories = {item["name"]: item["amount"] for item in current["expense_by_category"]}
    previous_categories = {item["name"]: item["amount"] for item in previous["expense_by_category"]}
    category_changes = []
    for name in sorted(set(current_categories) | set(previous_categories)):
        before = previous_categories.get(name, 0)
        after = current_categories.get(name, 0)
        change = after - before
        pct = (change / before * 100) if before else None
        category_changes.append({
            "name": name,
            "current": after,
            "current_formatted": rupiah(after),
            "previous": before,
            "previous_formatted": rupiah(before),
            "change": change,
            "change_formatted": rupiah(change),
            "change_percent": round(pct, 2) if pct is not None else None,
            "change_percent_formatted": percent(pct) if pct is not None else None,
        })
    category_changes.sort(key=lambda item: abs(item["change"]), reverse=True)
    expense_change_pct = None
    if previous["expense_total"] > 0:
        expense_change_pct = expense_change / previous["expense_total"] * 100

    today = datetime.now(TZ).date()
    elapsed_end = min(today + timedelta(days=1), end)
    elapsed_days = max(1, (elapsed_end - start).days)
    current["average_daily_expense"] = current["expense_total"] // elapsed_days

    obligations = obligations_list()
    due_in_period = [
        item
        for item in obligations
        if item["status"] in {"open", "partial", "overdue"}
        and item["due_date"]
        and start.isoformat() <= item["due_date"] < end.isoformat()
    ]

    return {
        "period": period,
        "label": label,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "current": current,
        "previous": {
            "start": prev_start.isoformat(),
            "end_exclusive": prev_end.isoformat(),
            **previous,
        },
        "comparison": {
            "expense_change": expense_change,
            "expense_change_formatted": rupiah(expense_change),
            "expense_change_percent": round(expense_change_pct, 2) if expense_change_pct is not None else None,
            "expense_change_percent_formatted": percent(expense_change_pct) if expense_change_pct is not None else None,
            "category_changes": category_changes,
        },
        "budgets": budget_status(anchor_date=anchor.isoformat(), period_type=period),
        "obligations_due": due_in_period,
        "wallets": _wallets_snapshot(),
        "goals": goals_list(status="active"),
    }


def report_text(data: dict[str, Any]) -> str:
    current = data["current"]
    comparison = data["comparison"]
    lines = [
        f"{data['period'].upper()} REPORT — {data['label']}",
        f"Expenses: {rupiah(current['expense_total'])}",
        f"Income: {rupiah(current['income_total'])}",
        f"Operating cash flow: {rupiah(current['operating_net'])}",
        f"Net balance movement: {rupiah(current['cash_movement'])}",
        f"Transaction count: {current['transaction_count']}",
        f"Average daily expense: {rupiah(current['average_daily_expense'])}",
    ]
    if comparison["expense_change_percent"] is None:
        lines.append("Comparison: the previous period has no expenses.")
    else:
        direction = "increased" if comparison["expense_change"] > 0 else "decreased" if comparison["expense_change"] < 0 else "did not change"
        lines.append(
            f"Comparison: expenses {direction} by {comparison['expense_change_percent_formatted']} "
            f"({comparison['expense_change_formatted']}) from the previous period."
        )

    significant_changes = [item for item in comparison.get("category_changes", []) if item["change"] != 0][:5]
    if significant_changes:
        lines.extend(["", "Largest category changes:"])
        for item in significant_changes:
            direction = "+" if item["change"] > 0 else ""
            lines.append(f"- {item['name']}: {direction}{item['change_formatted']} versus the previous period")

    lines.extend(["", "Expenses by category:"])
    if current["expense_by_category"]:
        lines.extend(
            f"- {item['name']}: {item['amount_formatted']}"
            for item in current["expense_by_category"]
        )
    else:
        lines.append("- No expenses yet.")

    lines.extend(["", "Expenses by wallet:"])
    if current["expense_by_wallet"]:
        lines.extend(
            f"- {item['name']}: {item['amount_formatted']}"
            for item in current["expense_by_wallet"]
        )
    else:
        lines.append("- No expenses yet.")

    if data["budgets"]:
        lines.extend(["", "Budget status:"])
        lines.extend(
            f"- {item['category']}: {item['spent_formatted']} / {item['limit_formatted']} "
            f"({item['usage_percent_formatted']})"
            for item in data["budgets"]
        )

    if data["obligations_due"]:
        lines.extend(["", "Bills, debts, or receivables due in this period:"])
        lines.extend(
            f"- #{item['id']} {item['name']}: {item['remaining_amount_formatted']} — "
            f"{item['due_date']} ({item['status']})"
            for item in data["obligations_due"]
        )

    financing = []
    if current["debt_borrowed"]:
        financing.append(f"debt received {rupiah(current['debt_borrowed'])}")
    if current["debt_repaid"]:
        financing.append(f"debt repaid {rupiah(current['debt_repaid'])}")
    if current["loans_given"]:
        financing.append(f"money lent {rupiah(current['loans_given'])}")
    if current["loans_collected"]:
        financing.append(f"receivables collected {rupiah(current['loans_collected'])}")
    if financing:
        lines.extend(["", "Financing flows: " + ", ".join(financing) + "."])
    return "\n".join(lines)


def safe_to_spend(anchor_date: str | None = None) -> dict[str, Any]:
    today = date.fromisoformat(anchor_date) if anchor_date else datetime.now(TZ).date()
    month_start, month_end, _ = period_bounds("month", today)
    conn = connect()
    wallets = all_wallet_balances(conn)
    liquid_balance = sum(item["balance"] for item in wallets)
    conn.close()

    obligations = obligations_list()
    due_before_month_end = sum(
        item["remaining_amount"]
        for item in obligations
        if item["kind"] in {"bill", "debt_payable"}
        and item["status"] in {"open", "partial", "overdue"}
        and item["due_date"]
        and item["due_date"] < month_end.isoformat()
    )
    minimum_reserve = int(get_setting("minimum_reserve", "0") or 0)
    monthly_target = int(get_setting("monthly_savings_target", "0") or 0)

    conn = connect()
    start_dt = datetime.combine(month_start, time.min, TZ).isoformat(timespec="seconds")
    end_dt = datetime.combine(month_end, time.min, TZ).isoformat(timespec="seconds")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(se.amount),0) AS total
        FROM savings_entries se
        WHERE se.occurred_at>=? AND se.occurred_at<?
        """,
        (start_dt, end_dt),
    ).fetchone()
    conn.close()
    saved_this_month = max(0, int(row["total"]))
    savings_remaining = max(0, monthly_target - saved_this_month)
    goal_allocations = total_allocated_active()
    safe = liquid_balance - due_before_month_end - minimum_reserve - savings_remaining - goal_allocations
    days_left = max(1, (month_end - today).days)
    daily = safe // days_left if safe > 0 else 0
    return {
        "as_of": today.isoformat(),
        "liquid_balance": liquid_balance,
        "liquid_balance_formatted": rupiah(liquid_balance),
        "unpaid_bills_and_debts_due": due_before_month_end,
        "unpaid_bills_and_debts_due_formatted": rupiah(due_before_month_end),
        "minimum_reserve": minimum_reserve,
        "minimum_reserve_formatted": rupiah(minimum_reserve),
        "monthly_savings_target": monthly_target,
        "saved_this_month": saved_this_month,
        "remaining_savings_target": savings_remaining,
        "remaining_savings_target_formatted": rupiah(savings_remaining),
        "virtual_goal_allocations": goal_allocations,
        "virtual_goal_allocations_formatted": rupiah(goal_allocations),
        "safe_to_spend": safe,
        "safe_to_spend_formatted": rupiah(safe),
        "days_left_in_month": days_left,
        "daily_estimate": daily,
        "daily_estimate_formatted": rupiah(daily),
        "is_estimate": True,
        "warning": "This estimate is accurate only when all balances, bills, debts, and transactions are recorded.",
    }
