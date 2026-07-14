#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_BASE="${HERMES_HOME:-$HOME/.hermes}"
FINANCE_DIR="$HERMES_BASE/finance"
SKILL_DIR="$HERMES_BASE/skills/productivity/personal-finance"
SCRIPTS_DIR="$HERMES_BASE/scripts"
UPGRADE_DIR="$FINANCE_DIR/upgrades"
STAMP="$(date +%Y%m%d-%H%M%S)"

command -v python3 >/dev/null 2>&1 || {
  echo "python3 not found." >&2
  exit 1
}

mkdir -p "$FINANCE_DIR" "$SKILL_DIR/scripts" "$SCRIPTS_DIR" "$UPGRADE_DIR"

# Create a consistent SQLite backup before installation when data already exists.
if [[ -f "$FINANCE_DIR/finance.db" ]]; then
  BACKUP_PATH="$UPGRADE_DIR/pre-install-$STAMP.db"
  python3 - "$FINANCE_DIR/finance.db" "$BACKUP_PATH" <<'PY'
import sqlite3, sys
source, target = sys.argv[1], sys.argv[2]
src = sqlite3.connect(source)
dst = sqlite3.connect(target)
src.backup(dst)
dst.close()
src.close()
print(f"Pre-install database backup: {target}")
PY
fi

# Preserve the previous application files without touching the database.
if [[ -f "$FINANCE_DIR/finance.py" ]]; then
  mkdir -p "$UPGRADE_DIR/app-$STAMP"
  cp -a "$FINANCE_DIR/finance.py" "$UPGRADE_DIR/app-$STAMP/" || true
  [[ -d "$FINANCE_DIR/cali_finance" ]] && cp -a "$FINANCE_DIR/cali_finance" "$UPGRADE_DIR/app-$STAMP/" || true
fi

rm -rf "$FINANCE_DIR/cali_finance.new"
cp -a "$SOURCE_DIR/cali_finance" "$FINANCE_DIR/cali_finance.new"
rm -rf "$FINANCE_DIR/cali_finance"
mv "$FINANCE_DIR/cali_finance.new" "$FINANCE_DIR/cali_finance"
install -m 700 "$SOURCE_DIR/finance.py" "$FINANCE_DIR/finance.py"

install -m 600 "$SOURCE_DIR/skill/SKILL.md" "$SKILL_DIR/SKILL.md"
install -m 700 "$SOURCE_DIR/skill/scripts/finance.sh" "$SKILL_DIR/scripts/finance.sh"

for script in "$SOURCE_DIR"/scripts/*.sh; do
  install -m 700 "$script" "$SCRIPTS_DIR/$(basename "$script")"
done

python3 "$FINANCE_DIR/finance.py" init
python3 "$FINANCE_DIR/finance.py" health

cat <<EOF

Cali Finance installed.

App       : $FINANCE_DIR/finance.py
Database  : $FINANCE_DIR/finance.db
Skill     : $SKILL_DIR/SKILL.md
Cron files: $SCRIPTS_DIR/finance-*.sh

Next steps:
  1. Restart gateway: hermes gateway restart
  2. Send in Telegram: /reset
  3. Test: /personal-finance show all wallet balances

Optional OCR:
  cd "$SOURCE_DIR" && ./install-ocr.sh

The installer does not change SOUL.md or Cali's personality.
EOF
