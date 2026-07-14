from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DASHBOARD_DIR, TZ
from .goals import goals_list
from .ledger import all_wallet_balances
from .db import connect
from .money import rupiah
from .obligations import obligations_list
from .reports import report_data, safe_to_spend


def _bar_rows(items: list[dict[str, Any]], value_key: str = "amount") -> str:
    if not items:
        return '<p class="muted">No data yet.</p>'
    maximum = max(int(item.get(value_key, 0)) for item in items) or 1
    rows = []
    for item in items:
        value = int(item.get(value_key, 0))
        width = max(2, round(value / maximum * 100))
        label = html.escape(str(item.get("name", "-")))
        formatted = html.escape(str(item.get(f"{value_key}_formatted", rupiah(value))))
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{label}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width}%"></div></div>'
            f'<div class="bar-value">{formatted}</div></div>'
        )
    return "".join(rows)


def dashboard_generate(
    *,
    output_path: str | None = None,
    period: str = "month",
    anchor_date: str | None = None,
) -> str:
    data = report_data(period, anchor_date)
    safe = safe_to_spend(anchor_date)
    conn = connect()
    wallets = all_wallet_balances(conn)
    conn.close()
    obligations = obligations_list()
    open_obligations = [item for item in obligations if item["status"] in {"open", "partial", "overdue"}]
    goals = goals_list()
    current = data["current"]
    generated = datetime.now(TZ).strftime("%d %B %Y %H:%M WIB")

    wallet_cards = "".join(
        f'<div class="mini-card"><span>{html.escape(item["name"])}</span>'
        f'<strong>{html.escape(item["balance_formatted"])}</strong>'
        f'<small>{html.escape(item["kind"])}</small></div>'
        for item in wallets
    ) or '<p class="muted">No wallets yet.</p>'

    obligation_rows = "".join(
        f'<tr><td>#{item["id"]}</td><td>{html.escape(item["name"])}</td>'
        f'<td>{html.escape(item["kind"])}</td><td>{html.escape(item["remaining_amount_formatted"])}</td>'
        f'<td>{html.escape(item["due_date"] or "-")}</td><td><span class="status {html.escape(item["status"])}">{html.escape(item["status"])}</span></td></tr>'
        for item in open_obligations[:20]
    ) or '<tr><td colspan="6" class="muted">No open bills or debts.</td></tr>'

    goal_rows = "".join(
        f'<div class="goal"><div><strong>{html.escape(item["name"])}</strong>'
        f'<span>{html.escape(item["current_formatted"])} / {html.escape(item["target_formatted"])}</span></div>'
        f'<div class="progress"><i style="width:{min(100, item["progress_percent"])}%"></i></div></div>'
        for item in goals
    ) or '<p class="muted">No savings goals yet.</p>'

    top_rows = "".join(
        f'<tr><td>{html.escape(item["occurred_at"][:10])}</td><td>{html.escape(item["description"])}</td>'
        f'<td>{html.escape(item["category"] or "-")}</td><td>{html.escape(item["wallet"])}</td>'
        f'<td class="num">{html.escape(item["amount_formatted"])}</td></tr>'
        for item in current["top_expenses"]
    ) or '<tr><td colspan="5" class="muted">No transactions yet.</td></tr>'

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    document = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cali Dashboard</title>
<style>
:root {{ color-scheme: dark; --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3; --muted:#8b949e; --accent:#7ee787; --warn:#d29922; --danger:#f85149; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1180px; margin:auto; padding:28px 18px 60px; }} h1,h2,p {{ margin-top:0; }} h1 {{ font-size:clamp(28px,5vw,48px); margin-bottom:6px; }} h2 {{ font-size:18px; }}
.muted {{ color:var(--muted); }} .grid {{ display:grid; gap:14px; }} .metrics {{ grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); margin:22px 0; }}
.card,.metric,.mini-card {{ background:var(--panel); border:1px solid var(--border); border-radius:14px; }} .card {{ padding:18px; }} .metric {{ padding:18px; }} .metric span,.mini-card span {{ color:var(--muted); display:block; font-size:13px; }} .metric strong {{ display:block; font-size:24px; margin-top:7px; }}
.two {{ grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); }} .wallets {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px; }} .mini-card {{ padding:13px; }} .mini-card strong {{ display:block;font-size:18px;margin:5px 0; }} .mini-card small {{ color:var(--muted); }}
.bar-row {{ display:grid;grid-template-columns:130px 1fr 105px;align-items:center;gap:10px;margin:11px 0;font-size:13px; }} .bar-track {{ height:10px;background:#21262d;border-radius:999px;overflow:hidden; }} .bar-fill {{ height:100%;background:var(--accent);border-radius:inherit; }} .bar-value,.num {{ text-align:right; }}
table {{ width:100%;border-collapse:collapse;font-size:13px; }} th,td {{ padding:10px;border-bottom:1px solid var(--border);text-align:left; }} .table-wrap {{ overflow:auto; }}
.status {{ border:1px solid var(--border);border-radius:999px;padding:3px 8px;font-size:11px; }} .status.overdue {{ color:var(--danger); }} .status.partial {{ color:var(--warn); }}
.goal {{ margin:14px 0; }} .goal>div:first-child {{ display:flex;justify-content:space-between;gap:10px; }} .goal span {{ color:var(--muted);font-size:12px; }} .progress {{ height:9px;background:#21262d;border-radius:999px;overflow:hidden;margin-top:7px; }} .progress i {{ display:block;height:100%;background:var(--accent); }}
footer {{ color:var(--muted);font-size:12px;margin-top:20px; }} @media(max-width:600px) {{ .bar-row {{ grid-template-columns:90px 1fr; }} .bar-value {{ grid-column:2;text-align:left; }} }}
</style>
</head>
<body><main>
<p class="muted">Cali • {html.escape(data["label"])}</p>
<h1>Your finances, without the unnecessary drama.</h1>
<p class="muted">Generated {html.escape(generated)}. This static dashboard reads only the local database.</p>
<section class="grid metrics">
<div class="metric"><span>Expenses</span><strong>{rupiah(current["expense_total"])}</strong></div>
<div class="metric"><span>Income</span><strong>{rupiah(current["income_total"])}</strong></div>
<div class="metric"><span>Operating cash flow</span><strong>{rupiah(current["operating_net"])}</strong></div>
<div class="metric"><span>Safe to spend (estimate)</span><strong>{html.escape(safe["safe_to_spend_formatted"])}</strong></div>
</section>
<section class="card"><h2>Wallet balances</h2><div class="wallets">{wallet_cards}</div></section>
<section class="grid two" style="margin-top:14px">
<div class="card"><h2>Expenses by category</h2>{_bar_rows(current["expense_by_category"])}</div>
<div class="card"><h2>Expenses by wallet</h2>{_bar_rows(current["expense_by_wallet"])}</div>
</section>
<section class="grid two" style="margin-top:14px">
<div class="card"><h2>Savings goals</h2>{goal_rows}</div>
<div class="card"><h2>Safe-to-spend estimate</h2>
<p><strong>{html.escape(safe["safe_to_spend_formatted"])}</strong> through the end of the month, about <strong>{html.escape(safe["daily_estimate_formatted"])}</strong> per day.</p>
<p class="muted">Bills/debts due: {html.escape(safe["unpaid_bills_and_debts_due_formatted"])} • Minimum reserve: {html.escape(safe["minimum_reserve_formatted"])} • Goal allocations: {html.escape(safe["virtual_goal_allocations_formatted"])}</p></div>
</section>
<section class="card" style="margin-top:14px"><h2>Open bills, debts, and receivables</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Remaining</th><th>Due date</th><th>Status</th></tr></thead><tbody>{obligation_rows}</tbody></table></div></section>
<section class="card" style="margin-top:14px"><h2>Largest expenses</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Description</th><th>Category</th><th>Wallet</th><th>Amount</th></tr></thead><tbody>{top_rows}</tbody></table></div></section>
<footer>Do not expose this dashboard to the public internet. Access it only through an SSH tunnel.</footer>
<script type="application/json" id="finance-data">{payload}</script>
</main></body></html>'''

    output = Path(output_path).expanduser() if output_path else DASHBOARD_DIR / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return str(output.resolve())
