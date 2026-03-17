from __future__ import annotations

import sqlite3
import threading
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.utils.contacts import normalize_phone


@dataclass(frozen=True)
class DncEntry:
    number: str
    added_ts: float
    source: str
    reason: str
    message: Optional[str]


class DncRegistry:
    """
    Persistent Do-Not-Contact (DNC) / opt-out registry.

    Primary use:
    - Block future outbound sends to recipients who opted out.
    - Record why/how the entry was added for operator review.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._closed = False

        if path != ":memory:":
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dnc_registry (
                number TEXT PRIMARY KEY,
                added_ts REAL NOT NULL,
                source TEXT NOT NULL,
                reason TEXT NOT NULL,
                message TEXT
            )
            """
        )
        self._conn.commit()
        self._finalizer = weakref.finalize(self, DncRegistry._close_connection, self._conn)

    @staticmethod
    def _close_connection(conn: sqlite3.Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            finalizer = getattr(self, "_finalizer", None)
        try:
            if finalizer is not None and finalizer.alive:
                finalizer()
            else:
                self._close_connection(self._conn)
        except Exception:
            pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _normalize(number: str | None) -> str:
        if not number:
            return ""
        normalized = normalize_phone(str(number), min_length=1)
        return normalized or "".join(ch for ch in str(number) if ch.isdigit())

    def add(
        self,
        number: str,
        *,
        source: str = "manual",
        reason: str = "opt_out",
        message: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        n = self._normalize(number)
        if not n:
            return {"ok": False, "error": "Invalid number"}

        now = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO dnc_registry (number, added_ts, source, reason, message)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(number) DO UPDATE SET
                    added_ts=excluded.added_ts,
                    source=excluded.source,
                    reason=excluded.reason,
                    message=excluded.message
                """,
                (n, now, (source or "manual"), (reason or "opt_out"), message),
            )
            self._conn.commit()
        return {"ok": True, "number": n}

    def remove(self, number: str) -> Dict[str, Any]:
        n = self._normalize(number)
        if not n:
            return {"ok": False, "error": "Invalid number"}
        with self._lock:
            cur = self._conn.execute("DELETE FROM dnc_registry WHERE number = ?", (n,))
            self._conn.commit()
            removed = int(cur.rowcount or 0)
        return {"ok": True, "number": n, "removed": removed}

    def is_blocked(self, number: str | None) -> bool:
        n = self._normalize(number)
        if not n:
            return False
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM dnc_registry WHERE number = ? LIMIT 1", (n,))
            return cur.fetchone() is not None

    def get(self, number: str) -> Optional[DncEntry]:
        n = self._normalize(number)
        if not n:
            return None
        with self._lock:
            cur = self._conn.execute(
                "SELECT number, added_ts, source, reason, message FROM dnc_registry WHERE number = ?",
                (n,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return DncEntry(
            number=str(row[0]),
            added_ts=float(row[1]),
            source=str(row[2]),
            reason=str(row[3]),
            message=str(row[4]) if row[4] is not None else None,
        )

    def list_recent(self, *, limit: int = 50) -> List[DncEntry]:
        lim = max(1, min(int(limit), 500))
        with self._lock:
            cur = self._conn.execute(
                "SELECT number, added_ts, source, reason, message FROM dnc_registry ORDER BY added_ts DESC LIMIT ?",
                (lim,),
            )
            rows = cur.fetchall() or []
        out: List[DncEntry] = []
        for number, added_ts, source, reason, message in rows:
            out.append(
                DncEntry(
                    number=str(number),
                    added_ts=float(added_ts),
                    source=str(source),
                    reason=str(reason),
                    message=str(message) if message is not None else None,
                )
            )
        return out

