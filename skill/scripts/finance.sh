#!/usr/bin/env bash
set -euo pipefail
HERMES_BASE="${HERMES_HOME:-$HOME/.hermes}"
APP="${HERMES_FINANCE_APP:-$HERMES_BASE/finance/finance.py}"
exec python3 "$APP" "$@"
