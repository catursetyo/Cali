#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(tempfile.mkdtemp(prefix="cali-finance-migration-"))
os.environ["HERMES_HOME"] = str(ROOT / ".hermes")
DB = ROOT / ".hermes" / "finance" / "finance.db"
DB.parent.mkdir(parents=True)

conn = sqlite3.connect(DB)
conn.executescript(
    """
    CREATE TABLE wallets(
      id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE,kind TEXT,
      opening_balance INTEGER,active INTEGER,created_at TEXT
    );
    CREATE TABLE wallet_aliases(alias TEXT PRIMARY KEY,wallet_id INTEGER);
    CREATE TABLE categories(
      id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE,type TEXT,
      active INTEGER,created_at TEXT
    );
    CREATE TABLE category_aliases(alias TEXT PRIMARY KEY,category_id INTEGER);
    CREATE TABLE transactions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,occurred_at TEXT NOT NULL,
      type TEXT NOT NULL CHECK(type IN ('expense','income','transfer')),
      amount INTEGER NOT NULL,category_id INTEGER,wallet_id INTEGER NOT NULL,
      to_wallet_id INTEGER,description TEXT NOT NULL,note TEXT,raw_input TEXT,
      source TEXT,status TEXT,created_at TEXT,voided_at TEXT,void_reason TEXT
    );
    INSERT INTO wallets VALUES(1,'Cash','cash',100000,1,'2026-01-01');
    INSERT INTO categories VALUES(1,'Makan','expense',1,'2026-01-01');
    INSERT INTO transactions VALUES(
      1,'2026-07-01T12:00:00+07:00','expense',20000,1,1,NULL,
      'Bakso',NULL,NULL,'hermes','active','2026-07-01T12:00:00+07:00',NULL,NULL
    );
    """
)
conn.commit()
conn.close()

from cali_finance.db import connect, init_db
from cali_finance.ledger import all_wallet_balances, resolve_category

init_db()
conn = connect()
columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)")}
assert "fingerprint" in columns
assert conn.execute("SELECT amount FROM transactions WHERE id=1").fetchone()["amount"] == 20000
balances = all_wallet_balances(conn)
assert next(item for item in balances if item["name"] == "Cash")["balance"] == 80000
assert resolve_category(conn, "Food")["name"] == "Makan"
assert conn.execute("SELECT COUNT(*) FROM categories WHERE name='Food'").fetchone()[0] == 0
conn.close()
print(f"MIGRATION_OK {ROOT}")
