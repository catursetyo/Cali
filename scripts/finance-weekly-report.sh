#!/usr/bin/env bash
set -euo pipefail
exec python3 "${HERMES_HOME:-$HOME/.hermes}/finance/finance.py" report --period week
