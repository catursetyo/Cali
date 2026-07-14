# AGENTS.md

## Purpose

This is the primary instruction file for Codex when developing, testing,
documenting, and publishing **Cali**. Keep it in the
repository root beside `README.md`, `finance.py`, and `cali_finance/`.

If more `AGENTS.md` files are added later, the instructions nearest to the file
being changed take precedence.

## Project Summary

Cali is a local personal finance ledger for Hermes Agent.

- The AI model understands natural language and selects commands.
- Python validates input and enforces business rules.
- SQLite is the source of truth for transactions and history.
- The Hermes skill explains when and how to use commands.
- Telegram is only the conversational interface.
- An Azure VM is the deployment runtime.
- GitHub stores only source code, documentation, and sanitized examples.

This project is not business accounting software, a tax application,
investment advice, direct bank-login synchronization, or a place to store user
financial data on GitHub.

## Priorities

Use this order when making technical decisions:

1. Financial data integrity.
2. Security and privacy.
3. Backward compatibility and safe migrations.
4. Deterministic, testable behavior.
5. Maintainability.
6. Hermes/Telegram user experience.
7. New features and convenience.

Never sacrifice the first five priorities for UI, personality, or attractive
features.

## Non-Negotiable Rules

### Never put sensitive data in the repository

Do not read, copy, create fixtures from, or commit:

- `~/.hermes/finance/finance.db`;
- `*.db`, `*.sqlite`, `*.sqlite3`, WAL, or SHM files;
- database backups;
- real receipt images;
- real bank statements or transaction exports;
- `~/.hermes/.env` or `~/.hermes/state.db`;
- Telegram or Nous Portal tokens;
- model API keys;
- Azure credentials;
- GitHub tokens;
- private SSH or `age` keys;
- `rclone.conf`;
- SAS tokens or storage account keys;
- account/card numbers, PINs, or passwords.

Use synthetic data in tests, examples, documentation, screenshots, and issues.

### Never mutate the Azure runtime as a side effect

The local repository is the source of truth. Do not develop primarily by
editing installed files in:

```text
~/.hermes/finance/
~/.hermes/skills/
~/.hermes/scripts/
```

Edit the repository, test, commit, then deploy through `install.sh`. Never run
SSH, `scp`, Azure deployment, gateway restarts, or remote commands unless the
user explicitly requests them.

### Never perform destructive Git operations

Without explicit instructions, do not:

- `git push`;
- create a GitHub repository, release, or tag;
- change repository visibility;
- delete branches or remotes;
- force-push;
- run `git reset --hard` or `git clean -fd`;
- rewrite history;
- delete unrelated user files.

Never force-push `main`.

### Never claim success without evidence

A change succeeds only when the relevant command exits with code `0`, relevant
tests pass, output is inspected, and `git diff` contains no unintended changes.
If a test cannot run, explain why honestly.

## Language and Communication

- Communicate with users in English unless asked otherwise.
- Be direct and not overly formal.
- Use English for source code, identifiers, commit messages, API/CLI options,
  and user documentation.
- Do not hide risks or failures behind optimistic wording.
- End tasks with changed files, tests run, and remaining risks.

## Repository Map

Expected structure:

```text
.
├── AGENTS.md
├── CHANGELOG.md
├── LICENSE
├── README.md
├── SECURITY.md
├── .env.example
├── .gitattributes
├── .gitignore
├── .github/workflows/test.yml
├── cali_finance/
│   ├── __init__.py
│   ├── alerts.py
│   ├── backup.py
│   ├── budgets.py
│   ├── cli.py
│   ├── config.py
│   ├── dashboard.py
│   ├── db.py
│   ├── goals.py
│   ├── imports.py
│   ├── ledger.py
│   ├── money.py
│   ├── obligations.py
│   ├── receipts.py
│   ├── reports.py
│   └── settings.py
├── examples/SOUL.example.md
├── finance.py
├── install.sh
├── install-ocr.sh
├── scripts/
├── skill/
│   ├── SKILL.md
│   └── scripts/
├── tests/
│   ├── migration_test.py
│   ├── restore_test.py
│   └── smoke_test.py
└── uninstall.sh
```

Do not move files without a strong reason. Structural changes must update all
affected installers, tests, README sections, skill instructions, and CI jobs.

## Module Responsibilities

- `cli.py`: argument parsing, command routing, and output serialization.
- `db.py`: schema, connections, migrations, integrity checks, transactions.
- `ledger.py`: transactions, wallets, categories, reconciliation, search, void.
- `money.py`: amount parsing and formatting.
- `budgets.py`: budgets and thresholds.
- `obligations.py`: bills, debts, receivables, payments, recurring obligations.
- `goals.py`: virtual savings goals.
- `reports.py`: report aggregation and safe-to-spend.
- `imports.py`: preview, row review, commit, deduplication, CSV export.
- `receipts.py`: OCR preview and receipt confirmation.
- `backup.py`: backup, restore, offsite backup, and retention.
- `alerts.py`: alert data and text output.
- `dashboard.py`: static dashboard from aggregated data.
- `settings.py`: stored configuration.
- `skill/SKILL.md`: Hermes usage instructions, never business logic.
- `scripts/`: non-interactive cron wrappers.
- `tests/`: synthetic data and isolated `HERMES_HOME` values.

Business rules must live in Python so they can be tested, not only in prompts
or `skill/SKILL.md`.

## Architecture Principles

### Local-first

Financial data stays in `HERMES_HOME` by default. A new feature must not send
data to web APIs, analytics, telemetry, other models, or external storage
without an explicit, documented user action.

### SQLite is the source of truth

Chat history, Markdown, memory, dashboards, CSV exports, and model responses are
not sources of truth. Every financial change must create structured records and
a clear audit trail.

### Integer rupiah amounts

- Store amounts as integers, never floats.
- Abbreviations such as `25rb` or `1,5jt` must parse to integers.
- Display Indonesian rupiah consistently.
- Normal transactions use positive amounts; the transaction type determines
  direction. Negative values are allowed only where the domain requires them.

### Date and time

- Default to `Asia/Jakarta`.
- Store timezone-aware datetimes.
- Accept validated absolute dates in the CLI.
- The agent resolves phrases such as "yesterday" before invoking the CLI.
- Weekly reports run Monday through Sunday unless requirements explicitly
  change.

### Auditability

Avoid updates or deletes that erase history. Use voids for incorrect
transactions, adjustments for reconciliation, payment records for settlements,
statuses for cancellations, and schema versions for migrations.

## Financial Domain Rules

### Transactions

- Expenses and income require a wallet, amount, description, and category.
- Transfers between wallets are neither expenses nor income.
- Never guess an omitted wallet or amount.
- Hermes may infer a category; Python must validate it.
- Duplicate detection warns instead of silently deleting a possibly valid
  transaction. Overrides must be explicit.

### Bills

An unpaid bill is an obligation, not an actual expense. Create the expense only
when a full or partial payment occurs. Bills support due dates, partial
payments, `open`/`paid`/`overdue`/`cancelled` states, a default wallet,
category, provider/counterparty, and audited payments.

### Debts and receivables

- `payable`: the user owes another party.
- `receivable`: another party owes the user.
- Borrowed funds increase a wallet without becoming income.
- Lent funds decrease a wallet without becoming an expense.
- Principal repayment/collection is not expense/income.
- Record fees, interest, and penalties separately when supported.

### Budgets

Budgets do not change balances. Thresholds must be deterministic and alerts
must not repeat without clear controls. Periods/timezones must stay consistent.
Overall and per-category budgets must not double count report values.

### Savings goals

Goals are virtual buckets. Contributions do not change wallet balances unless
a real transfer is recorded. UI and responses must state this clearly.

### Safe-to-spend

Safe-to-spend is an estimate. Implement and test its formula in Python,
document its components, and expose its assumptions.

## Database and Migrations

Before changing the schema:

1. Study the current schema and migrations in `db.py`.
2. Ensure valid v1/v2 databases still migrate.
3. Never drop data-bearing tables or columns without a migration plan.
4. Keep migrations idempotent and as safe as possible after partial failures.
5. Use SQLite transactions for multi-step changes.
6. Update the schema version.
7. Add or update migration tests.

Every schema or semantic change must test a fresh database, an older database,
preserved old data, correct post-migration balances, foreign keys,
`PRAGMA integrity_check`, and pre-migration backup creation.

Backup/restore changes must preserve input validation, explicit confirmation,
post-restore integrity checks, no silent overwrite, and temporary-directory
tests.

## CLI Contract

The CLI is the interface between Hermes and business logic.

- Keep option names stable and consistent.
- Use JSON for machine-readable output except text reports.
- Operational errors exit non-zero with actionable, secret-safe messages.
- Do not print tracebacks for normal input errors.
- Do not change JSON fields used by the skill without a compatibility plan.
- Dangerous commands require explicit confirmation.
- Cron commands are non-interactive.
- Keep `--help` useful.
- Document new commands in `cli.py`, `README.md`, and `skill/SKILL.md`.

Entry points:

```bash
python3 finance.py
python3 ~/.hermes/finance/finance.py
```

## Hermes Skill

`skill/SKILL.md` must explain when to use the skill, provide deterministic
procedures, require questions for missing material data, forbid invented
results, use correct CLI commands, preserve raw user input where appropriate,
require preview/confirmation for OCR/import/reconciliation, distinguish bills,
debts, receivables, transfers, income, and expenses, keep Telegram responses
short, and contain no secrets or personal data.

Audit every skill example after changing CLI commands. Personality and jokes
must never replace validation, amounts, errors, or confirmation.

## OCR and CSV Import

Tesseract is optional and core tests must not depend on it. OCR produces only a
preview and never records a transaction automatically. Confirmation requires
at least amount, date, wallet, category, and description. Receipt files stay in
the runtime data directory; use only synthetic receipts in the repository.

CSV imports follow:

```text
preview -> inspect/update rows -> explicit commit
```

Preview must not create transactions. Preserve auditable source/batch data,
deduplicate with an external ID and/or fingerprint, never silently classify an
ambiguous row as `Other`, keep commit as idempotent as practical, and test with
synthetic CSV files in temporary directories.

## Backup and Offsite Backup

Local and offsite backups are separate. Keep local backups, encrypt before
offsite upload, never store private encryption keys or `rclone` credentials in
the repository, support offline restore after the archive is available,
document retention, alert on backup age, and never call a backup safe before an
integrity check passes.

## Coding Style

### Python

- Target Python 3.11 and 3.12; prefer the standard library.
- Add dependencies only when necessary and explain them.
- Type public functions and complex structures.
- Use `pathlib.Path`, context managers, and explicit connection cleanup.
- Avoid mutable global state.
- Bind SQL values with parameters; allowlist dynamic identifiers.
- Keep functions small and focused; avoid decorative abstractions.
- Keep error messages specific and foreign keys enabled.
- Use `except Exception` only at a boundary that converts errors to CLI output,
  and never swallow errors silently.

### Shell

Use:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

Quote expansions, guard destructive commands, keep cron non-interactive and
installers idempotent, never delete the active database, and use LF endings.

### SQL

Use transactions for multi-table operations. Add indexes only for actual
queries. Treat foreign keys and constraints as business rules. Explain
non-trivial schema changes.

## Testing

Required commands from the repository root:

```bash
python3 -m compileall -q cali_finance finance.py
python3 tests/smoke_test.py
python3 tests/migration_test.py
python3 tests/restore_test.py
```

Expected markers:

```text
SMOKE_OK
MIGRATION_OK
RESTORE_OK
```

Every test uses a temporary `HERMES_HOME` and must not read the real
`~/.hermes`, change user data, use credentials/internet/Telegram/Azure, send
data externally, or depend on test order.

Add tests when changing amount parsing, balances, duplicate detection, reports,
budgets, obligations, recurring rules, safe-to-spend, imports, receipts,
backup/restore, migrations, or CLI output contracts. Add a regression test for
bug fixes when practical.

Before finishing, run:

```bash
git status --short
git diff --check
git diff --stat
```

Then inspect the actual diff.

## Documentation

Behavior changes update relevant files: `README.md`, `skill/SKILL.md`,
`CHANGELOG.md`, `SECURITY.md`, `.env.example`, cron scripts, and sanitized
examples. Do not document untested commands or include server IPs, personal
usernames/paths, credentials, real amounts/transactions, or private screenshots.
Use placeholders such as `USER_VM`, `PUBLIC_IP`, `USERNAME`, and `KEY_NAME.pem`.

## Git Workflow

Before work:

```bash
git status --short
git branch --show-current
git remote -v
```

Preserve uncommitted user changes. Avoid editing unrelated dirty files.

For non-trivial work, suggest `feat/<name>`, `fix/<name>`, `docs/<name>`, or
`chore/<name>`. Do not create a branch for a small requested change on the
active branch unless risk is high.

Use Conventional Commits, for example:

```text
feat: add debt repayment tracking
fix: preserve wallet balance during migration
docs: add GitHub publishing guide
test: cover partial bill payments
refactor: isolate report aggregation
chore: configure GitHub Actions
```

Commits must be focused, secret-free, runtime-data-free, tested, and must not
mix mass formatting with behavior changes without a reason. Do not commit
unless asked or clearly required by the task.

Before pushing, inspect staged state and scan for secrets/sensitive files:

```bash
git status
git diff --cached --check
git diff --cached --stat
git diff --cached

grep -RInE \
  'AIza|GEMINI_API_KEY|GOOGLE_API_KEY|TELEGRAM.*TOKEN|ghp_|github_pat_|BEGIN .*PRIVATE KEY|ACCOUNT_KEY|SAS_TOKEN' \
  . --exclude-dir=.git

find . -type f \( \
  -name '*.db' -o -name '*.sqlite*' -o -name '.env' -o \
  -name '*.pem' -o -name '*.key' -o -name 'rclone.conf' \
\)
```

Documentation placeholders are allowed; real credentials are not.

## GitHub Setup and Publication

When missing, Codex may help create `.gitignore`, `.gitattributes`,
`.env.example`, `SECURITY.md`, `.github/workflows/test.yml`, and
`examples/SOUL.example.md`.

`.gitignore` must cover Python caches/virtualenvs, real `.env` files, databases
and WAL/SHM, backups, receipts, real imports/exports, credentials, private
keys, release archives, and editor metadata. Sanitized examples/docs may be
tracked.

CI runs on push and pull requests with Python 3.11/3.12, compileall, smoke,
migration, and restore tests, `contents: read`, no secrets, and no real data.

Recommend a private repository initially. Do not make it public until the user
reviews the license, README, security policy, full history, secret scans,
example data, attribution, and issue-readiness.

Publication checklist:

- [ ] Root `AGENTS.md` exists.
- [ ] README covers purpose, features, install, upgrade, and limits.
- [ ] LICENSE owner is correct and SECURITY.md exists.
- [ ] `.gitignore` and `.env.example` are safe.
- [ ] `examples/SOUL.example.md` is sanitized.
- [ ] All tests pass.
- [ ] No databases, receipts, statements, or credentials exist in the tree or
      history.
- [ ] GitHub Actions passes and default branch is `main`.
- [ ] Secret scanning/push protection is enabled when available.
- [ ] Repository remains private until public audit completes.
- [ ] Upgrade instructions and migration/breaking-change release notes exist.
- [ ] Directly distributed release archives have checksums.

## Releases and Versioning

Use Semantic Versioning. PATCH is a backward-compatible fix, MINOR is a
backward-compatible feature, and MAJOR is a breaking or materially different
migration. The version source is `cali_finance/__init__.py`.

For a release: require a clean tree, choose the next version, update
`__init__.py` and `CHANGELOG.md`, update README if needed, run all available
tests and `git diff --check`, create a release commit and annotated tag, then
push only with user approval. GitHub release notes include changes, migrations,
upgrade steps, and known limitations. Archives get SHA-256 checksums and never
contain runtime data, receipts, configuration, or secrets.

Example only; never run without explicit instructions:

```bash
git tag -a v2.1.0 -m "Cali v2.1.0"
```

## Azure Deployment

Deployment is separate from GitHub publication:

```text
change local source
-> run tests
-> commit
-> push to GitHub
-> pull on Azure
-> stop gateway
-> run install.sh
-> start gateway
-> health check
```

Run deployment commands only when explicitly requested:

```bash
hermes gateway stop
./install.sh
hermes gateway start
hermes gateway status
python3 ~/.hermes/finance/finance.py health
```

The installer must create a pre-upgrade backup, preserve the old database,
migrate the schema, install source/skill/scripts, preserve `SOUL.md`, and never
delete user data. Suggest `/reset` in Telegram after deploying skill changes.

## Workflow for Every Task

1. Understand whether the request touches money, schema, backup, security, or
   release. Read the repository before asking answerable questions.
2. Inspect relevant files and Git state; never guess existing structure/APIs.
3. For non-trivial changes, state a short plan, files, tests, and
   migration/security risks.
4. Implement the minimum change, preserve APIs, avoid broad refactors and
   unnecessary dependencies.
5. Run the most specific test first, then the full suite.
6. Review the diff for leaks, command/schema/output mistakes, migration risks,
   documentation typos, line endings, executable bits, untracked files, and
   runtime data.
7. Report changes, tests, remaining risks, and next steps.

Preferred final format:

```text
Changes:
- ...

Tests:
- `command` — passed

Notes/Risks:
- ...

Next step:
- ...
```

Do not say the task is complete while tests fail or requirements remain open.

## Definition of Done

The requested behavior works; business rules live in Python; relevant tests
exist and pass; migrations are safe; docs and the Hermes skill agree; no real
data/secrets are present; `git diff --check` is clean; installer/cron still
work; Hermes can consume CLI output; remaining risks are explicit; and
publication/deployment happens only with explicit approval.

Act as a conservative financial-data maintainer. Prefer rejecting ambiguous
input, requesting confirmation, adding regression coverage, preserving history,
and stating risks over shipping a fast change that can damage balances,
transactions, backups, or privacy.
