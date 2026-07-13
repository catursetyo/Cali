from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
DATA_DIR = Path(os.environ.get("HERMES_FINANCE_DIR", HERMES_HOME / "finance")).expanduser()
DB_PATH = Path(os.environ.get("HERMES_FINANCE_DB", DATA_DIR / "finance.db")).expanduser()
BACKUP_DIR = DATA_DIR / "backups"
RECEIPT_DIR = DATA_DIR / "receipts"
IMPORT_DIR = DATA_DIR / "imports"
DASHBOARD_DIR = DATA_DIR / "dashboard"
TZ_NAME = os.environ.get("HERMES_FINANCE_TZ", "Asia/Jakarta")
TZ = ZoneInfo(TZ_NAME)
SCHEMA_VERSION = 2


def ensure_directories() -> None:
    for path in (DATA_DIR, BACKUP_DIR, RECEIPT_DIR, IMPORT_DIR, DASHBOARD_DIR):
        path.mkdir(parents=True, exist_ok=True)
