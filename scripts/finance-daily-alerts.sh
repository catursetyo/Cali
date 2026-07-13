#!/usr/bin/env bash
set -euo pipefail
APP="${HERMES_HOME:-$HOME/.hermes}/finance/finance.py"
python3 "$APP" recurring-run >/dev/null
exec python3 "$APP" alerts --new-only --mark-sent --format text
