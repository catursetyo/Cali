#!/usr/bin/env bash
set -euo pipefail
ANCHOR_DATE="$(date -d 'yesterday' +%F)"
exec python3 "${HERMES_HOME:-$HOME/.hermes}/finance/finance.py" report --period month --date "$ANCHOR_DATE"
