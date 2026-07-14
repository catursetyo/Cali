# Changelog

## Unreleased

- Restores an obligation's remaining amount and status when its payment
  transaction is voided.
- Commits receipt confirmation and its expense transaction atomically.
- Revalidates wallet balances atomically when confirming reconciliation so
  transactions recorded after preview cannot produce an incorrect balance.
- Renames the Hermes skill slash command from `/personal-finance` to `/cali`
  and removes the legacy installed skill during upgrades.
- Rejects symbolic links, hard links, and other special archive entries during
  restore to prevent extraction outside the temporary directory.
- Changes documentation, Hermes instructions, dashboard labels, installer
  output, reports, alerts, and CLI errors to English.
- Uses English default category names for new databases while preserving
  Indonesian aliases and existing database labels for compatibility.

## Initial release

- Adds a local SQLite ledger with safe schema initialization.
- Adds duplicate detection and explicit override.
- Adds reconciliation preview and audited adjustments.
- Adds category/overall budgets and threshold alerts.
- Adds unpaid bills, payable debts, receivables, and partial payments.
- Adds recurring bill generation.
- Adds previous-period report comparison and category deltas.
- Adds safe-to-spend estimation and configurable reserves.
- Adds virtual savings goals.
- Adds validated transaction search.
- Adds staged CSV import with duplicate detection.
- Adds receipt preview and optional local Tesseract OCR.
- Adds static HTML dashboard.
- Adds local/offsite backup and health alerts.
- Adds script-only cron helpers for Telegram delivery.
