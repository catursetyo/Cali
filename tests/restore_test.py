#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(tempfile.mkdtemp(prefix="cali-finance-restore-"))
os.environ["HERMES_HOME"] = str(ROOT / ".hermes")

from cali_finance.backup import _safe_tar_members, backup_local, restore_backup
from cali_finance.db import init_db
from cali_finance.ledger import add_transaction, recent_transactions, wallet_set

for link_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
    archive_path = ROOT / f"malicious-{link_type.decode()}.tar"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("finance.db")
        member.type = link_type
        member.linkname = "../../outside"
        archive.addfile(member)
    with tarfile.open(archive_path) as archive:
        try:
            list(_safe_tar_members(archive, ROOT / "extract"))
        except ValueError as exc:
            assert "Unsupported backup archive member type" in str(exc)
        else:
            raise AssertionError(f"Archive link type {link_type!r} was accepted")

init_db()
wallet_set("Cash", opening_balance_raw="100000")
add_transaction(
    tx_type="expense",
    amount_raw="10000",
    wallet_name="Cash",
    category_name="Food",
    description="Transaction before backup",
)
backup = backup_local()
add_transaction(
    tx_type="expense",
    amount_raw="20000",
    wallet_name="Cash",
    category_name="Food",
    description="Transaction after backup",
)
assert len(recent_transactions()) == 2
result = restore_backup(backup["path"], "RESTORE")
assert result["ok"]
assert len(recent_transactions()) == 1
print(f"RESTORE_OK {ROOT}")
