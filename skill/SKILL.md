---
name: cali
description: Record, audit, and summarize personal finances with wallets, budgets, bills, debts, receivables, savings goals, CSV files, and receipts.
version: 1.0.0
author: Cali Project
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [finance, expense, budgeting, debt, bills, savings, automation]
    category: productivity
    requires_toolsets: [terminal]
---

# Cali Personal Finance

Use this skill for all personal finance work: transactions, balances, budgets,
unpaid bills, debts, receivables, savings goals, reports, reconciliation, CSV
imports, and receipts.

Always use this CLI:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh COMMAND ...
```

The local SQLite database is the only source of truth. Never treat chat
messages, memory, Markdown, or model output as recorded transactions.

## Non-Negotiable Rules

1. Never invent an amount, date, category, wallet, balance, or result.
2. Never say "recorded," "paid," or "successful" before the CLI returns
   `"ok": true`.
3. Expenses and income require an amount, category, wallet, description, and
   date. The default date is the current date in Asia/Jakarta.
4. Infer a category only when it is clear. Ask when it is ambiguous.
5. Ask for an omitted wallet. Never choose Cash automatically.
6. Preserve the user's original wording with `--raw-input` when supported.
7. Never write SQL directly. Always use validated commands.
8. Transfers between wallets are not expenses or income.
9. Debt principal repayments are not consumer expenses. Receivable collections
   are not business income. The CLI tracks these financing flows separately.
10. Savings goals are virtual allocations; wallet balances change only when the
    user also records a real transfer.
11. Preview and request confirmation for risky actions:
    - suspected duplicate transactions;
    - reconciliation adjustments;
    - CSV import commits;
    - OCR receipt confirmations;
    - voiding transactions or cancelling bills/debts.
12. Never send the database or sensitive financial details to external web/API
    services without an explicit request.

## Record Transactions

Expense:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh add \
  --type expense \
  --amount 25000 \
  --category "Food" \
  --wallet "Cash" \
  --description "Meatball soup" \
  --date "2026-07-14" \
  --raw-input "I had Rp25,000 meatball soup for lunch, paid in cash"
```

Income:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh add \
  --type income \
  --amount 750000 \
  --category "Freelance" \
  --wallet "BCA" \
  --description "Project payment" \
  --raw-input "Rp750,000 freelance payment arrived in BCA"
```

If the result contains `code: possible_duplicate`, show the candidates and ask
whether this is a new transaction. Use `--force-duplicate` only after explicit
confirmation.

Keep a successful confirmation concise:

```text
Recorded #ID: Rp... — description
Category: ...
Wallet: ...
Date: ...
Wallet balance: ...
```

One light Cali remark is allowed, but amounts and status remain the focus.

## Transfers and Wallets

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh transfer \
  --amount 100000 --from-wallet BCA --to-wallet GoPay \
  --description "Top up GoPay"
```

List or add wallets:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh wallets
${HERMES_SKILL_DIR}/scripts/finance.sh wallet-add \
  --name "DANA" --kind ewallet --opening-balance 50000
```

Opening balances are only for onboarding, not daily balance corrections.

## Balance Reconciliation

Always preview first:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh reconcile \
  --wallet "GoPay" --actual-balance 142500
```

When there is a difference, explain the recorded balance, actual balance, and
difference. Ask whether to find the missing transaction or create an
adjustment. Only after explicit approval:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh reconcile-adjust \
  --check-id ID --reason "An older transaction was not recorded" \
  --confirm-adjust YES
```

## Budgets

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh budget-set \
  --category "Food" --limit 800000 --period month
${HERMES_SKILL_DIR}/scripts/finance.sh budgets
```

After recording an expense, check `budget_warnings`. Give a light warning at
70%, a firm warning at 90%, and a serious warning at 100% or more. Do not judge.

## Unpaid Bills

Recording a bill does not immediately create an expense:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh bill-add \
  --name "July internet" --amount 275000 \
  --due-date 2026-07-15 --category Bills --wallet BCA
```

When it is actually paid:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligation-pay \
  --id ID --amount 275000 --wallet BCA
```

Partial payments are supported. Show the remainder and status after payment.

## Debts and Receivables

`payable` means the user owes another party. `receivable` means another party
owes the user.

Debt without recording incoming funds:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh debt-add \
  --direction payable --name "Debt to Umar" \
  --counterparty Umar --amount 500000 --due-date 2026-08-01
```

If borrowed money really enters a tracked wallet, add `--cash-wallet BCA`. For
a receivable, `--cash-wallet Cash` means money left Cash when it was lent.

Debt repayment and receivable collection use the same command:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligation-pay \
  --id ID --amount 100000 --wallet BCA
```

List obligations:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh obligations
```

## Recurring Bills

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh recurring-add \
  --name "Netflix" --amount 65000 --category Subscriptions \
  --next-due-date 2026-08-07 --frequency monthly --wallet GoPay
```

`recurring-run` creates unpaid bills only. It never marks them paid.

## Savings Goals

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh goal-add \
  --name "Laptop" --target 10000000 --target-date 2027-01-01
${HERMES_SKILL_DIR}/scripts/finance.sh goal-contribute \
  --goal "Laptop" --amount 200000 --wallet BCA
```

Always explain that contributions are virtual allocations. If the user really
moves money to a dedicated account, record a separate transfer.

## Reports and Search

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh report --period week
${HERMES_SKILL_DIR}/scripts/finance.sh report --period month
${HERMES_SKILL_DIR}/scripts/finance.sh safe-to-spend
${HERMES_SKILL_DIR}/scripts/finance.sh search \
  --query coffee --from 2026-07-01 --to 2026-07-31 --wallet GoPay
```

Prioritize total expenses, income, operating cash flow, previous-period
comparison, category changes, budgets, bills/debts, and wallet details. Always
describe `safe-to-spend` as an estimate.

## CSV Import

Imports must start with a preview:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-preview \
  --file /absolute/path/statement.csv --wallet BCA --source "bca-july"
```

Show ready, unresolved, duplicate, and error counts. Do not commit while a
category remains unclear. Fix a row with:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-row-set \
  --row-id ID --type expense --category "Other"
```

Use `Other` only with the user's approval. Commit after confirmation:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh import-commit --batch-id ID
```

## Telegram Receipts

When Telegram provides an attachment path, preview it locally:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh receipt-scan \
  --file /absolute/path/receipt.jpg --wallet GoPay --ocr
```

Never save OCR output directly as a transaction. Show the detected merchant,
amount, date, category, and wallet, then ask the user to review them. After
approval:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh receipt-confirm \
  --id ID --wallet GoPay --category Food \
  --description "Purchase from receipt" --amount 74500 --date 2026-07-14
```

Ask for manual data when OCR is unavailable or unclear. Never pretend to read
an image.

## Corrections

List transactions, then void by ID:

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh list --limit 20
${HERMES_SKILL_DIR}/scripts/finance.sh void \
  --id ID --reason "Wrong amount; replaced by a new transaction"
```

Never edit history directly. Create a replacement transaction after voiding.

## Serious Mode

Stop joking when `alerts` or `health` reports:

- an unhealthy database;
- an unexpected negative balance;
- a large overdue bill/debt;
- a failed or stale backup;
- a problematic bulk import;
- possible data loss or corruption.

State what failed, its impact, and the next concrete action. Never hide a
serious problem behind personality.

## Verification

```bash
${HERMES_SKILL_DIR}/scripts/finance.sh health
${HERMES_SKILL_DIR}/scripts/finance.sh wallets
${HERMES_SKILL_DIR}/scripts/finance.sh obligations
${HERMES_SKILL_DIR}/scripts/finance.sh backup
```

Restore only after an explicit request, once the gateway is stopped and the
user identifies the correct archive. Use `restore --confirm RESTORE`; never run
it automatically or from an assumption.

If a command returns `"ok": false`, report the failure and do not claim the
action completed.
