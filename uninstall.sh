#!/usr/bin/env bash
set -euo pipefail
HERMES_BASE="${HERMES_HOME:-$HOME/.hermes}"
FINANCE_DIR="$HERMES_BASE/finance"
SKILL_DIR="$HERMES_BASE/skills/productivity/personal-finance"
SCRIPTS_DIR="$HERMES_BASE/scripts"

cat <<EOF
Safe uninstall removes only the application, skill, and cron helpers.
The database will NOT be deleted:
  $FINANCE_DIR/finance.db
EOF

read -r -p "Continue? Type YES: " confirm
[[ "$confirm" == "YES" ]] || exit 1

rm -rf "$FINANCE_DIR/cali_finance"
rm -f "$FINANCE_DIR/finance.py"
rm -rf "$SKILL_DIR"
rm -f "$SCRIPTS_DIR"/finance-weekly-report.sh \
      "$SCRIPTS_DIR"/finance-monthly-report.sh \
      "$SCRIPTS_DIR"/finance-daily-alerts.sh \
      "$SCRIPTS_DIR"/finance-backup.sh \
      "$SCRIPTS_DIR"/finance-offsite-backup.sh \
      "$SCRIPTS_DIR"/finance-dashboard-refresh.sh

echo "Application removed. Database preserved."
