from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .config import BACKUP_DIR, DB_PATH, RECEIPT_DIR, TZ
from .db import connect


def _safe_tar_members(archive: tarfile.TarFile, destination: Path):
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"Unsafe backup archive member: {member.name}")
        yield member


def backup_local(keep: int = 30) -> dict[str, Any]:
    if keep < 1:
        raise ValueError("At least one backup must be retained.")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S-%f")
    snapshot = BACKUP_DIR / f"finance-{stamp}.db"
    archive_path = BACKUP_DIR / f"cali-finance-{stamp}.tar.gz"

    source_conn = connect()
    target_conn = sqlite3.connect(snapshot)
    source_conn.backup(target_conn)
    target_conn.close()
    source_conn.close()

    manifest = {
        "format": "cali-finance-backup",
        "format_version": 1,
        "app_version": __version__,
        "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "database": "finance.db",
        "receipts_included": RECEIPT_DIR.exists(),
    }
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(snapshot, arcname="finance.db")
        if RECEIPT_DIR.exists():
            for item in RECEIPT_DIR.iterdir():
                if item.is_file():
                    archive.add(item, arcname=f"receipts/{item.name}")
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        info.mtime = int(datetime.now(TZ).timestamp())
        archive.addfile(info, io.BytesIO(payload))

    archives = sorted(BACKUP_DIR.glob("cali-finance-*.tar.gz"), reverse=True)
    for old_archive in archives[keep:]:
        stamp_part = old_archive.name.removeprefix("cali-finance-").removesuffix(".tar.gz")
        old_archive.unlink(missing_ok=True)
        (BACKUP_DIR / f"finance-{stamp_part}.db").unlink(missing_ok=True)

    now = manifest["created_at"]
    conn = connect()
    cursor = conn.execute(
        "INSERT INTO backup_log(path,created_at,offsite_status) VALUES(?,?,?)",
        (str(archive_path), now, "not_requested"),
    )
    log_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "backup_log_id": log_id,
        "path": str(archive_path),
        "database_snapshot": str(snapshot),
        "created_at": now,
        "size_bytes": archive_path.stat().st_size,
        "receipts_included": manifest["receipts_included"],
    }


def backup_offsite(keep: int = 30) -> dict[str, Any]:
    local = backup_local(keep=keep)
    source = Path(local["path"])
    remote = os.environ.get("FINANCE_RCLONE_REMOTE", "").strip()
    recipient = os.environ.get("FINANCE_BACKUP_AGE_RECIPIENT", "").strip()
    if not remote:
        raise ValueError(
            "FINANCE_RCLONE_REMOTE is not configured. Use an rclone crypt remote or Azure Blob."
        )
    rclone = shutil.which("rclone")
    if not rclone:
        raise ValueError("rclone is not installed.")

    upload_source = source
    encrypted = False
    if recipient:
        age = shutil.which("age")
        if not age:
            raise ValueError("age is not installed, but an encryption recipient is configured.")
        encrypted_path = source.with_suffix(source.suffix + ".age")
        result = subprocess.run(
            [age, "-r", recipient, "-o", str(encrypted_path), str(source)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(f"Backup encryption failed: {result.stderr.strip()}")
        upload_source = encrypted_path
        encrypted = True
    elif os.environ.get("ALLOW_PLAINTEXT_FINANCE_BACKUP") != "1":
        raise ValueError(
            "Plaintext offsite backup refused. Set FINANCE_BACKUP_AGE_RECIPIENT or ALLOW_PLAINTEXT_FINANCE_BACKUP=1."
        )

    destination = remote.rstrip("/") + "/" + upload_source.name
    result = subprocess.run(
        [rclone, "copyto", str(upload_source), destination],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    status = "success" if result.returncode == 0 else "failed"
    conn = connect()
    conn.execute(
        "UPDATE backup_log SET offsite_target=?,offsite_status=? WHERE id=?",
        (destination, status, local["backup_log_id"]),
    )
    conn.commit()
    conn.close()
    if result.returncode != 0:
        raise ValueError(f"Offsite upload failed: {result.stderr.strip()}")
    if encrypted:
        upload_source.unlink(missing_ok=True)
    return {
        **local,
        "offsite_target": destination,
        "offsite_status": status,
        "encrypted": encrypted,
    }


def restore_backup(archive_path: str, confirm: str) -> dict[str, Any]:
    if confirm != "RESTORE":
        raise ValueError("Restore requires --confirm RESTORE.")
    source = Path(archive_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise ValueError(f"Backup archive not found: {source}")

    safety = backup_local()
    with tempfile.TemporaryDirectory(prefix="cali-finance-restore-") as tmp:
        destination = Path(tmp)
        with tarfile.open(source, "r:*") as archive:
            archive.extractall(destination, members=_safe_tar_members(archive, destination))
        restored_db = destination / "finance.db"
        if not restored_db.exists():
            raise ValueError("The archive does not contain finance.db.")
        check_conn = sqlite3.connect(restored_db)
        integrity = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
        check_conn.close()
        if integrity != "ok":
            raise ValueError(f"The database in the backup is corrupt: {integrity}")

        replacement = DB_PATH.with_suffix(".db.restore")
        shutil.copy2(restored_db, replacement)
        DB_PATH.with_name(DB_PATH.name + "-wal").unlink(missing_ok=True)
        DB_PATH.with_name(DB_PATH.name + "-shm").unlink(missing_ok=True)
        os.replace(replacement, DB_PATH)

        restored_receipts = destination / "receipts"
        receipt_count = 0
        if restored_receipts.exists():
            RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
            for item in restored_receipts.iterdir():
                if item.is_file():
                    shutil.copy2(item, RECEIPT_DIR / item.name)
                    receipt_count += 1

    return {
        "ok": True,
        "restored_from": str(source),
        "safety_backup": safety["path"],
        "database": str(DB_PATH),
        "receipt_count": receipt_count,
        "warning": "Restart the Hermes gateway before using the skill again.",
    }


def last_backup() -> dict[str, Any] | None:
    conn = connect()
    row = conn.execute("SELECT * FROM backup_log ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None
