from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, SCHEMA_VERSION, TZ, ensure_directories
from .money import normalize

DEFAULT_WALLETS = [
    ("Cash", "cash", 0, ["cash", "tunai", "uang tunai"]),
    ("GoPay", "ewallet", 0, ["gopay", "go pay"]),
]

DEFAULT_CATEGORIES = [
    ("Makan", "expense", ["makan", "minum", "kuliner", "jajan", "kopi", "snack", "bakso", "restoran", "warung"]),
    ("Transportasi", "expense", ["transportasi", "transport", "bensin", "parkir", "ojol", "gojek", "grab", "tol"]),
    ("Kebutuhan Harian", "expense", ["kebutuhan harian", "sembako", "toiletries", "rumah tangga", "indomaret", "alfamart"]),
    ("Tagihan", "expense", ["tagihan", "listrik", "air", "internet", "pulsa", "paket data", "wifi"]),
    ("Pendidikan", "expense", ["pendidikan", "kuliah", "kursus", "buku", "kelas"]),
    ("Kesehatan", "expense", ["kesehatan", "obat", "dokter", "rumah sakit", "apotek"]),
    ("Sosial", "expense", ["sosial", "nongkrong", "hadiah", "traktir", "patungan"]),
    ("Hiburan", "expense", ["hiburan", "game", "film", "konser", "bioskop"]),
    ("Belanja", "expense", ["belanja", "pakaian", "elektronik", "aksesoris", "shopee", "tokopedia"]),
    ("Donasi", "expense", ["donasi", "sedekah", "amal"]),
    ("Langganan", "expense", ["langganan", "subscription", "netflix", "spotify", "youtube premium"]),
    ("Perawatan Diri", "expense", ["skincare", "salon", "barbershop", "potong rambut"]),
    ("Lainnya", "expense", ["lainnya", "lain-lain", "other"]),
    ("Gaji", "income", ["gaji", "salary"]),
    ("Bonus", "income", ["bonus"]),
    ("Hadiah", "income", ["hadiah masuk", "gift"]),
    ("Freelance", "income", ["freelance", "proyek", "project fee"]),
    ("Pemasukan Lainnya", "income", ["pemasukan lainnya", "income lainnya"]),
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_directories()
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not table_exists(conn, name):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({name})")}


def _create_transactions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            category_id INTEGER REFERENCES categories(id),
            wallet_id INTEGER NOT NULL REFERENCES wallets(id),
            to_wallet_id INTEGER REFERENCES wallets(id),
            description TEXT NOT NULL,
            note TEXT,
            raw_input TEXT,
            source TEXT NOT NULL DEFAULT 'hermes',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','void')),
            created_at TEXT NOT NULL,
            voided_at TEXT,
            void_reason TEXT,
            fingerprint TEXT,
            external_id TEXT,
            import_batch_id INTEGER,
            receipt_id INTEGER,
            metadata_json TEXT
        )
        """
    )


def _migrate_transactions(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "transactions"):
        _create_transactions(conn)
        return

    required = {
        "id", "occurred_at", "type", "amount", "category_id", "wallet_id",
        "to_wallet_id", "description", "note", "raw_input", "source", "status",
        "created_at", "voided_at", "void_reason", "fingerprint", "external_id",
        "import_batch_id", "receipt_id", "metadata_json",
    }
    existing = table_columns(conn, "transactions")
    if required.issubset(existing):
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE transactions RENAME TO transactions_legacy_v1")
    _create_transactions(conn)

    legacy = table_columns(conn, "transactions_legacy_v1")
    target_columns = [
        "id", "occurred_at", "type", "amount", "category_id", "wallet_id",
        "to_wallet_id", "description", "note", "raw_input", "source", "status",
        "created_at", "voided_at", "void_reason",
    ]
    usable = [column for column in target_columns if column in legacy]
    conn.execute(
        f"INSERT INTO transactions ({','.join(usable)}) "
        f"SELECT {','.join(usable)} FROM transactions_legacy_v1"
    )
    conn.execute("DROP TABLE transactions_legacy_v1")
    conn.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    ensure_directories()
    conn = connect()
    now = datetime.now(TZ).isoformat(timespec="seconds")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            kind TEXT NOT NULL DEFAULT 'other',
            opening_balance INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wallet_aliases (
            alias TEXT PRIMARY KEY COLLATE NOCASE,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            type TEXT NOT NULL CHECK(type IN ('expense','income')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS category_aliases (
            alias TEXT PRIMARY KEY COLLATE NOCASE,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE
        );
        """
    )

    _migrate_transactions(conn)

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER REFERENCES categories(id),
            period_type TEXT NOT NULL DEFAULT 'month' CHECK(period_type IN ('month','week')),
            limit_amount INTEGER NOT NULL CHECK(limit_amount > 0),
            start_date TEXT NOT NULL,
            end_date TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            alert_70 INTEGER NOT NULL DEFAULT 1,
            alert_90 INTEGER NOT NULL DEFAULT 1,
            alert_100 INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(category_id, period_type, start_date)
        );

        CREATE TABLE IF NOT EXISTS balance_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id),
            recorded_balance INTEGER NOT NULL,
            actual_balance INTEGER NOT NULL,
            difference INTEGER NOT NULL,
            checked_at TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','adjusted','closed')),
            adjustment_transaction_id INTEGER REFERENCES transactions(id)
        );

        CREATE TABLE IF NOT EXISTS obligations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('bill','debt_payable','debt_receivable')),
            name TEXT NOT NULL,
            counterparty TEXT,
            original_amount INTEGER NOT NULL CHECK(original_amount > 0),
            remaining_amount INTEGER NOT NULL CHECK(remaining_amount >= 0),
            category_id INTEGER REFERENCES categories(id),
            default_wallet_id INTEGER REFERENCES wallets(id),
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','partial','paid','overdue','cancelled')),
            recurring_rule_id INTEGER,
            note TEXT,
            raw_input TEXT,
            created_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS obligation_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obligation_id INTEGER NOT NULL REFERENCES obligations(id) ON DELETE CASCADE,
            transaction_id INTEGER REFERENCES transactions(id),
            amount INTEGER NOT NULL CHECK(amount > 0),
            paid_at TEXT NOT NULL,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id),
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS recurring_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            category_id INTEGER NOT NULL REFERENCES categories(id),
            default_wallet_id INTEGER REFERENCES wallets(id),
            frequency TEXT NOT NULL CHECK(frequency IN ('weekly','monthly','yearly')),
            interval_count INTEGER NOT NULL DEFAULT 1 CHECK(interval_count > 0),
            next_due_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recurring_occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL REFERENCES recurring_rules(id) ON DELETE CASCADE,
            due_date TEXT NOT NULL,
            obligation_id INTEGER NOT NULL REFERENCES obligations(id),
            created_at TEXT NOT NULL,
            UNIQUE(rule_id, due_date)
        );

        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            target_amount INTEGER NOT NULL CHECK(target_amount > 0),
            current_amount INTEGER NOT NULL DEFAULT 0 CHECK(current_amount >= 0),
            target_date TEXT,
            linked_wallet_id INTEGER REFERENCES wallets(id),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','paused','cancelled')),
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS savings_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL CHECK(amount != 0),
            occurred_at TEXT NOT NULL,
            wallet_id INTEGER REFERENCES wallets(id),
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS finance_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id),
            status TEXT NOT NULL DEFAULT 'preview' CHECK(status IN ('preview','committed','cancelled')),
            total_rows INTEGER NOT NULL DEFAULT 0,
            valid_rows INTEGER NOT NULL DEFAULT 0,
            unresolved_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            committed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS import_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            occurred_at TEXT,
            type TEXT,
            amount INTEGER,
            description TEXT,
            category_id INTEGER REFERENCES categories(id),
            external_id TEXT,
            raw_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('ready','unresolved','duplicate','error','committed','skipped')),
            error_message TEXT,
            transaction_id INTEGER REFERENCES transactions(id),
            UNIQUE(batch_id, row_number)
        );

        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            merchant TEXT,
            occurred_at TEXT,
            total_amount INTEGER,
            category_id INTEGER REFERENCES categories(id),
            wallet_id INTEGER REFERENCES wallets(id),
            ocr_text TEXT,
            status TEXT NOT NULL DEFAULT 'preview' CHECK(status IN ('preview','committed','rejected')),
            transaction_id INTEGER REFERENCES transactions(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notification_events (
            event_key TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_sent_at TEXT,
            payload_json TEXT
        );

        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            offsite_target TEXT,
            offsite_status TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_occurred_at ON transactions(occurred_at);
        CREATE INDEX IF NOT EXISTS idx_transactions_status_type ON transactions(status, type);
        CREATE INDEX IF NOT EXISTS idx_transactions_fingerprint ON transactions(fingerprint);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_external_id_unique
            ON transactions(external_id) WHERE external_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_obligations_status_due ON obligations(status, due_date);
        CREATE INDEX IF NOT EXISTS idx_import_rows_batch_status ON import_rows(batch_id, status);
        """
    )

    for name, kind, opening, aliases in DEFAULT_WALLETS:
        conn.execute(
            "INSERT OR IGNORE INTO wallets(name, kind, opening_balance, created_at) VALUES(?,?,?,?)",
            (name, kind, opening, now),
        )
        wallet_id = conn.execute(
            "SELECT id FROM wallets WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()["id"]
        for alias in aliases + [name]:
            conn.execute(
                "INSERT OR IGNORE INTO wallet_aliases(alias, wallet_id) VALUES(?,?)",
                (normalize(alias), wallet_id),
            )

    for name, category_type, aliases in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories(name, type, created_at) VALUES(?,?,?)",
            (name, category_type, now),
        )
        category_id = conn.execute(
            "SELECT id FROM categories WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()["id"]
        for alias in aliases + [name]:
            conn.execute(
                "INSERT OR IGNORE INTO category_aliases(alias, category_id) VALUES(?,?)",
                (normalize(alias), category_id),
            )

    defaults = {
        "minimum_reserve": "0",
        "monthly_savings_target": "0",
        "duplicate_window_days": "1",
        "backup_stale_hours": "48",
        "due_soon_days": "3",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO finance_settings(key, value, updated_at) VALUES(?,?,?)",
            (key, value, now),
        )

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    conn.close()


def db_integrity() -> dict:
    conn = connect()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_errors = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
    version = conn.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()
    conn.close()
    return {
        "integrity": integrity,
        "foreign_key_errors": fk_errors,
        "schema_version": int(version["value"]) if version else None,
        "database": str(DB_PATH),
    }


def json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
