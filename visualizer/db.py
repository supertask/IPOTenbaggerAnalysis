"""SQLite index for visualizer.

The index is built by `python -m visualizer.build_index`. Visualizer components
call `get_conn()` and fall back to raw TSV reads if the DB is missing or has an
incompatible schema.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

BASE_DIR = Path(__file__).parent.parent
INDEX_DIR = BASE_DIR / "data" / "output" / "index"
DB_PATH = INDEX_DIR / "visualizer.db"

_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.Lock()
_startup_checked = False


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn() -> Optional[sqlite3.Connection]:
    """Return a shared read-only connection, or None if the DB is unusable."""
    global _conn, _startup_checked
    with _conn_lock:
        if _conn is not None:
            return _conn
        if not DB_PATH.exists():
            if not _startup_checked:
                logger.warning("[index] db not found at %s, falling back to raw TSV", DB_PATH)
                _startup_checked = True
            return None
        try:
            conn = _open_readonly(DB_PATH)
            version = conn.execute(
                "SELECT value FROM build_meta WHERE key='schema_version'"
            ).fetchone()
            if version is None or version["value"] != SCHEMA_VERSION:
                logger.warning(
                    "[index] schema_version mismatch (db=%s expected=%s), falling back to raw TSV",
                    version["value"] if version else None,
                    SCHEMA_VERSION,
                )
                conn.close()
                return None
            _conn = conn
            if not _startup_checked:
                built_at = conn.execute(
                    "SELECT value FROM build_meta WHERE key='built_at'"
                ).fetchone()
                logger.info(
                    "[index] using %s (built_at=%s)",
                    DB_PATH,
                    built_at["value"] if built_at else "?",
                )
                _startup_checked = True
            return _conn
        except sqlite3.Error as exc:
            logger.warning("[index] failed to open %s: %s", DB_PATH, exc)
            return None


def close() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            _conn.close()
            _conn = None
