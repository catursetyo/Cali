#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="cali-finance-restore-"))
os.environ["HERMES_HOME"] = str(ROOT / ".hermes")

from cali_finance.backup import backup_local, restore_backup
from cali_finance.db import init_db
from cali_finance.ledger import add_transaction, recent_transactions, wallet_set

init_db()
wallet_set("Cash", opening_balance_raw="100000")
add_transaction(
    tx_type="expense",
    amount_raw="10000",
    wallet_name="Cash",
    category_name="Makan",
    description="Transaksi sebelum backup",
)
backup = backup_local()
add_transaction(
    tx_type="expense",
    amount_raw="20000",
    wallet_name="Cash",
    category_name="Makan",
    description="Transaksi setelah backup",
)
assert len(recent_transactions()) == 2
result = restore_backup(backup["path"], "RESTORE")
assert result["ok"]
assert len(recent_transactions()) == 1
print(f"RESTORE_OK {ROOT}")
