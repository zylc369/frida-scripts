"""SQLite database layer for frida-device-app-script-bind storage."""

import sqlite3
import time
from pathlib import Path

from . import config
from .log import log


def _get_conn() -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating parent dirs if needed."""
    config.FRIDA_BASE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.FRIDA_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create the frida_device_app_script_bind table and indexes if they don't exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS frida_device_app_script_bind (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                create_time  INTEGER NOT NULL,
                modify_time  INTEGER NOT NULL,
                device_type  TEXT    NOT NULL,
                device_id    TEXT    NOT NULL,
                app_identity TEXT    NOT NULL,
                script_path  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_device_app
            ON frida_device_app_script_bind (device_id, app_identity)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_identity
            ON frida_device_app_script_bind (app_identity)
        """)
        conn.commit()
    finally:
        conn.close()


def query_scripts(device_type: str, app_identity: str) -> list[dict]:
    """Query bound scripts for a given device_type + app_identity.

    Returns rows sorted by create_time DESC.
    Each row is a dict with keys: id, create_time, modify_time, device_type,
    device_id, app_identity, script_path.
    """
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """
            SELECT id, create_time, modify_time, device_type, device_id,
                   app_identity, script_path
            FROM frida_device_app_script_bind
            WHERE device_type = ? AND app_identity = ?
            ORDER BY create_time DESC
            """,
            (device_type, app_identity),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def add_script(
    device_type: str,
    device_id: str,
    app_identity: str,
    script_path: str,
) -> int | None:
    """Insert a new script binding.

    Returns the new row id on success, or None if a duplicate already exists
    (same device_type + app_identity + script_path combination).
    """
    now_ms = int(time.time() * 1000)
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """
            SELECT id FROM frida_device_app_script_bind
            WHERE device_type = ? AND app_identity = ? AND script_path = ?
            LIMIT 1
            """,
            (device_type, app_identity, script_path),
        )
        if cursor.fetchone() is not None:
            return None

        cursor = conn.execute(
            """
            INSERT INTO frida_device_app_script_bind
                (create_time, modify_time, device_type, device_id, app_identity, script_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now_ms, now_ms, device_type, device_id, app_identity, script_path),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_script(script_id: int) -> bool:
    """Delete a script binding by its primary key id.

    Returns True if a row was deleted, False otherwise.
    """
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM frida_device_app_script_bind WHERE id = ?",
            (script_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def check_duplicate(
    device_type: str,
    app_identity: str,
    script_path: str,
) -> bool:
    """Return True if a binding with the given combination already exists."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """
            SELECT 1 FROM frida_device_app_script_bind
            WHERE device_type = ? AND app_identity = ? AND script_path = ?
            LIMIT 1
            """,
            (device_type, app_identity, script_path),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()
