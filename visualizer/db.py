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

SCHEMA_VERSION = "3"

BASE_DIR = Path(__file__).parent.parent
INDEX_DIR = BASE_DIR / "data" / "output" / "index"
DB_PATH = INDEX_DIR / "visualizer.db"

_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.Lock()
_startup_checked = False
# 開いているDBファイルの更新時刻。build_index は別ファイルに書いてから
# 差し替えるので、掴んだままだと古い（あるいは消えた）ファイルを読み続ける
_conn_mtime: Optional[float] = None


def _mtime() -> Optional[float]:
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return None


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn() -> Optional[sqlite3.Connection]:
    """Return a shared read-only connection, or None if the DB is unusable."""
    global _conn, _startup_checked, _conn_mtime
    with _conn_lock:
        current = _mtime()
        if _conn is not None:
            if current == _conn_mtime:
                return _conn
            # インデックスが焼き直された。開き直さないと、差し替え前の
            # ファイルを読み続けて画面から表が消える
            logger.info("[index] db が更新されたので開き直します")
            try:
                _conn.close()
            except sqlite3.Error:
                pass
            _conn, _conn_mtime = None, None
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
            _conn, _conn_mtime = conn, current
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
    global _conn, _conn_mtime
    with _conn_lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        _conn_mtime = None
