# Cali Finance for Hermes Agent

Cali Finance is a local personal finance ledger for Hermes Agent. The AI model
understands natural language and selects commands, while Python and SQLite
handle validation, balances, reports, duplicate detection, and history.

## Features

- Multi-wallet income, expenses, and transfers.
- Automatic category inference with validation.
- Duplicate transaction detection with explicit overrides.
- Balance reconciliation with an audited adjustment trail.
- Weekly/monthly budgets with 70/90/100% warnings.
- Unpaid bills and partial payments.
- Payable debts and receivables.
- Recurring bills that create obligations, not fictional transactions.
- Weekly/monthly reports with previous-period comparisons.
- Safe-to-spend estimates.
- Virtual savings goals.
- Validated transaction search.
- Staged CSV import: preview, review, then commit.
- Receipt preview with optional local Tesseract OCR.
- Static HTML dashboard.
- Local backups and encrypted offsite backups through `age` and `rclone`.
- Alerts for budgets, due dates, negative balances, backups, and database health.

## Limitations

This is not business accounting software, a tax application, or investment
advice. Direct bank-login synchronization is not included; bank data is
imported from CSV. Receipt OCR is heuristic and always requires confirmation.
Savings goals are virtual buckets, not real money transfers.

## Requirements

- Linux with Python 3.11 or 3.12.
- Hermes Agent for Telegram use.
- Tesseract only for receipt OCR.
- `age` and `rclone` only for offsite backups.

Runtime data is stored in `~/.hermes/finance/` by default. Never put databases,
receipts, transaction exports, `.env` files, or credentials in this repository.

## Run from Source

1. Clone the repository and enter the project directory.

   ```bash
   git clone REPOSITORY_URL cali-finance
   cd cali-finance
   ```

2. Check the Python version.

   ```bash
   python3 --version
   ```

3. Initialize the local database.

   ```bash
   python3 finance.py init
   ```

4. Check database health and initial data.

   ```bash
   python3 finance.py health
   python3 finance.py wallets
   python3 finance.py categories --type expense
   ```

5. Add a wallet and record the first transaction.

   ```bash
   python3 finance.py wallet-add \
     --name BCA --kind bank --opening-balance 1000000

   python3 finance.py add \
     --type expense --amount 25000 --category Food \
     --wallet Cash --description "Meatball soup"
   ```

6. Review balances and transactions.

   ```bash
   python3 finance.py wallets
   python3 finance.py list --limit 10
   ```

Use synthetic data while testing the repository. Commands without a custom
`HERMES_HOME` use the default `~/.hermes` location.

## Install for Hermes Agent

1. Upload or clone the source on the Hermes host and enter the project folder.

   ```bash
   unzip cali-finance.zip
   cd cali-finance
   ```

2. Stop the gateway so no transaction arrives during installation.

   ```bash
   hermes gateway stop
   ```

3. Run the installer.

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

4. Restart the gateway and check its status.

   ```bash
   hermes gateway start
   hermes gateway status
   ```

5. Reload the skill and test it from Telegram.

   ```text
   /reset
   /personal-finance show all wallet balances
   ```

The installer preserves `~/.hermes/finance/finance.db`, creates a pre-install
database backup when one already exists, initializes/migrates the schema, runs
a health check, and does not change `SOUL.md` or Cali's personality.

For upgrades, repeat the same stop/install/start flow. Existing Indonesian
default category labels are preserved to avoid rewriting financial data; the
new English names are added as aliases, so English commands continue to work.

## Verify the Installation

```bash
python3 ~/.hermes/finance/finance.py health
python3 ~/.hermes/finance/finance.py wallets
python3 ~/.hermes/finance/finance.py categories --type expense
python3 ~/.hermes/finance/finance.py backup
```

## Natural-Language Examples

### Transactions

```text
Record a Rp25,000 chicken meal paid from GoPay.
I received Rp750,000 in freelance income in BCA.
Transfer Rp100,000 from BCA to GoPay.
Find all coffee purchases this month.
```

### Budgets

```text
Limit this month's food spending to Rp800,000.
Show the status of all my budgets.
```

### Bills, debts, and receivables

```text
Record a Rp275,000 internet bill due July 15 from BCA.
I just paid that internet bill in full from BCA.
I owe Umar Rp500,000, due August 1.
Zaki owes me Rp200,000 and the money came from Cash.
I received a Rp50,000 installment from Zaki into Cash.
```

### Reconciliation

```text
My actual GoPay balance is Rp142,500. Reconcile it with the ledger.
```

Cali shows the difference first. No adjustment is created without confirmation.

### Reports

```text
Summarize my finances this week.
Compare this month's expenses with last month.
How much is safe to spend through the end of the month?
```

## Important CLI Commands

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP add --type expense --amount 25000 --category Food \
  --wallet Cash --description "Meatball soup"

$APP transfer --amount 100000 --from-wallet BCA --to-wallet GoPay

$APP reconcile --wallet GoPay --actual-balance 142500
$APP reconcile-adjust --check-id 1 --reason "Missing transaction" --confirm-adjust YES

$APP budget-set --category Food --limit 800000 --period month
$APP budgets

$APP bill-add --name "July internet" --amount 275000 \
  --due-date 2026-07-15 --category Bills --wallet BCA

$APP debt-add --direction payable --name "Debt to Umar" \
  --amount 500000 --counterparty Umar --due-date 2026-08-01

$APP debt-add --direction receivable --name "Loan to Zaki" \
  --amount 200000 --counterparty Zaki --cash-wallet Cash

$APP obligations
$APP obligation-pay --id 1 --amount 100000 --wallet BCA

$APP recurring-add --name Netflix --amount 65000 \
  --category Subscriptions --next-due-date 2026-08-07 \
  --frequency monthly --wallet GoPay

$APP goal-add --name Laptop --target 10000000 --target-date 2027-01-01
$APP goal-contribute --goal Laptop --amount 200000 --wallet BCA

$APP report --period week
$APP report --period month
$APP safe-to-spend
```

## Safe-to-Spend Configuration

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP config-set --key minimum_reserve --value 400000
$APP config-set --key monthly_savings_target --value 500000
$APP config
```

The estimate subtracts bills/debts due, the minimum reserve, the remaining
monthly savings target, and virtual goal allocations from liquid balances. It
is always an estimate.

## CSV Import

Bank CSV formats vary. The importer detects common headers such as `date`,
`description`, `debit`, `credit`, `amount`, and `reference`. Legacy Indonesian
headers remain supported.

```bash
APP="python3 ~/.hermes/finance/finance.py"

$APP import-preview \
  --file ~/bank-statement.csv \
  --wallet BCA \
  --source "bca-2026-07" \
  --date-format '%d/%m/%Y'
```

Review rows:

```bash
$APP import-rows --batch-id 1
```

Resolve an unclear category:

```bash
$APP import-row-set --row-id 3 --type expense --category Shopping
```

Commit only after review:

```bash
$APP import-commit --batch-id 1
```

External IDs and fingerprints prevent duplicate imports.

## Receipt OCR

Install the optional dependency:

```bash
cd ~/cali-finance
./install-ocr.sh
```

Preview a receipt:

```bash
APP="python3 ~/.hermes/finance/finance.py"
$APP receipt-scan --file ~/receipt.jpg --wallet GoPay --ocr
```

Confirm only after checking the amount, date, category, and wallet:

```bash
$APP receipt-confirm --id 1 --wallet GoPay --category Food \
  --description "Purchase from receipt" --amount 74500 --date 2026-07-14
```

Hermes Telegram supports image/file attachments, but the skill still needs a
server-accessible path. Enter the data manually when the attachment is
unavailable or OCR is unclear.

## Local Dashboard

```bash
python3 ~/.hermes/finance/finance.py dashboard-generate
cd ~/.hermes/finance/dashboard
python3 -m http.server 8765 --bind 127.0.0.1
```

Create an SSH tunnel from your laptop:

```bash
ssh -L 8765:127.0.0.1:8765 -i ~/Downloads/azure-key.pem azureuser@PUBLIC_IP
```

Open `http://127.0.0.1:8765`. Never expose port 8765 to the public internet.

## Hermes Cron

Script-only cron jobs do not use model tokens. The installer copies the helper
scripts to `~/.hermes/scripts/`.

```bash
# Daily alerts at 08:00
hermes cron create "0 8 * * *" --no-agent \
  --script finance-daily-alerts.sh --deliver telegram \
  --name "Cali finance alerts"

# Weekly report on Sunday at 20:00
hermes cron create "0 20 * * 0" --no-agent \
  --script finance-weekly-report.sh --deliver telegram \
  --name "Weekly finance report"

# Previous-month report on day 1 at 08:10
hermes cron create "10 8 1 * *" --no-agent \
  --script finance-monthly-report.sh --deliver telegram \
  --name "Monthly finance report"

# Local backup every night
hermes cron create "30 2 * * *" --no-agent \
  --script finance-backup.sh --deliver local \
  --name "Finance database backup"

# Dashboard refresh
hermes cron create "15 7 * * *" --no-agent \
  --script finance-dashboard-refresh.sh --deliver local \
  --name "Finance dashboard refresh"
```

Set the VM timezone:

```bash
sudo timedatectl set-timezone Asia/Jakarta
```

## Offsite Backup

Each local backup is a `.tar.gz` archive containing a SQLite snapshot and
receipt files. The dashboard is omitted because it can be regenerated. A backup
on the same VM is insufficient. Offsite support uses `rclone` and requires
`age` encryption by default.

```bash
sudo apt install -y rclone age
rclone config
```

Configure a remote, ideally an `rclone crypt` remote backed by Azure Blob or
another storage provider:

```bash
cat >> ~/.hermes/.env <<'EOF'
FINANCE_RCLONE_REMOTE=mycrypt:cali-finance
FINANCE_BACKUP_AGE_RECIPIENT=age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
```

Test it:

```bash
set -a
source ~/.hermes/.env
set +a
python3 ~/.hermes/finance/finance.py backup --offsite
```

Never commit `.env`, SAS tokens, or private keys.

## Tests

Run from the repository root:

```bash
python3 -m compileall -q cali_finance finance.py
python3 tests/smoke_test.py
python3 tests/migration_test.py
python3 tests/restore_test.py
```

Expected final markers are `SMOKE_OK`, `MIGRATION_OK`, and `RESTORE_OK`. Every
test uses a temporary `HERMES_HOME` and needs no internet or credentials.

## Important Runtime Files

```text
~/.hermes/finance/finance.py
~/.hermes/finance/cali_finance/
~/.hermes/finance/finance.db
~/.hermes/finance/backups/
~/.hermes/finance/receipts/
~/.hermes/finance/dashboard/index.html
~/.hermes/skills/productivity/personal-finance/SKILL.md
~/.hermes/scripts/finance-*.sh
```

## Restore a Backup

Restore is destructive. Stop the gateway first so no transaction arrives:

```bash
hermes gateway stop
python3 ~/.hermes/finance/finance.py restore \
  --archive ~/.hermes/finance/backups/cali-finance-YYYYMMDD-HHMMSS.tar.gz \
  --confirm RESTORE
hermes gateway start
```

The restore command creates a safety backup of the current database, validates
the archived database, then restores the database and receipt files.
