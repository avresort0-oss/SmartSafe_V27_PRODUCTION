from __future__ import annotations

import sqlite3
import threading
import time
import weakref
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from core.utils.contacts import normalize_phone


@dataclass(frozen=True)
class RecipientSendState:
    recipient: str
    account: str
    last_sent_ts: Optional[float]
    hour_window_start_ts: float
    hour_count: int
    day_window_start_ts: float
    day_count: int


class RecipientHistoryStore:
    """
    SQLite-backed, lightweight per-recipient counters (cross-campaign).

    Design goals:
    - Very cheap reads (single row lookup)
    - Bounded row growth (one row per recipient+account key)
    - Thread-safe for MultiEngine worker threads (single process)
    """

    GLOBAL_ACCOUNT_KEY = "*"  # special key for cross-account recipient caps

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
            CREATE TABLE IF NOT EXISTS recipient_counters (
                recipient TEXT NOT NULL,
                account TEXT NOT NULL,
                last_sent_ts REAL,
                hour_window_start_ts REAL NOT NULL,
                hour_count INTEGER NOT NULL,
                day_window_start_ts REAL NOT NULL,
                day_count INTEGER NOT NULL,
                updated_ts REAL NOT NULL,
                PRIMARY KEY (recipient, account)
            )
            """
        )
        self._conn.commit()
        self._finalizer = weakref.finalize(self, RecipientHistoryStore._close_connection, self._conn)

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
    def _normalize_key(recipient: str | None) -> str:
        if not recipient:
            return ""
        normalized = normalize_phone(str(recipient), min_length=1)
        return normalized or str(recipient)

    @staticmethod
    def _account_key(account: str | None) -> str:
        return (account or "").strip().lower()

    @staticmethod
    def _day_start_ts(now_ts: float) -> float:
        dt = datetime.fromtimestamp(now_ts)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _read_row(self, recipient: str, account: str) -> Optional[Tuple]:
        cur = self._conn.execute(
            """
            SELECT recipient, account, last_sent_ts, hour_window_start_ts, hour_count, day_window_start_ts, day_count
            FROM recipient_counters
            WHERE recipient = ? AND account = ?
            """,
            (recipient, account),
        )
        return cur.fetchone()

    def get_state(
        self,
        recipient: str,
        *,
        account: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> RecipientSendState:
        now = now_ts if now_ts is not None else time.time()
        recipient_key = self._normalize_key(recipient)
        akey = self._account_key(account)

        with self._lock:
            row = self._read_row(recipient_key, akey)

        day_start = self._day_start_ts(now)
        if not row:
            return RecipientSendState(
                recipient=recipient_key,
                account=akey,
                last_sent_ts=None,
                hour_window_start_ts=now,
                hour_count=0,
                day_window_start_ts=day_start,
                day_count=0,
            )

        _recipient, _account, last_sent_ts, hour_start, hour_count, stored_day_start, day_count = row

        # Normalize windows to "now" view without mutating storage.
        if now - float(hour_start) >= 3600:
            hour_start = now
            hour_count = 0

        if float(stored_day_start) != float(day_start):
            stored_day_start = day_start
            day_count = 0

        return RecipientSendState(
            recipient=recipient_key,
            account=akey,
            last_sent_ts=float(last_sent_ts) if last_sent_ts is not None else None,
            hour_window_start_ts=float(hour_start),
            hour_count=int(hour_count),
            day_window_start_ts=float(stored_day_start),
            day_count=int(day_count),
        )

    def _can_send_for_key(
        self,
        recipient: str,
        *,
        account_key: str,
        min_interval_s: int,
        hourly_limit: int,
        daily_limit: int,
        now_ts: float,
    ) -> Tuple[bool, str]:
        state = self.get_state(recipient, account=account_key, now_ts=now_ts)

        if state.last_sent_ts is not None and min_interval_s > 0:
            elapsed = now_ts - state.last_sent_ts
            if elapsed < min_interval_s:
                remaining = int(min_interval_s - elapsed)
                return False, f"Too soon for same recipient (wait {remaining}s)"

        if hourly_limit > 0 and state.hour_count >= hourly_limit:
            return False, "Per-recipient hourly limit reached"

        if daily_limit > 0 and state.day_count >= daily_limit:
            return False, "Per-recipient daily limit reached"

        return True, "OK"

    def can_send(
        self,
        recipient: str,
        *,
        account: Optional[str] = None,
        min_interval_s: int,
        hourly_limit: int,
        daily_limit: int,
        now_ts: Optional[float] = None,
    ) -> Tuple[bool, str]:
        now = now_ts if now_ts is not None else time.time()

        # Always enforce a cross-account (global) cap so account rotation cannot
        # bypass per-recipient throttles.
        ok, reason = self._can_send_for_key(
            recipient,
            account_key=self.GLOBAL_ACCOUNT_KEY,
            min_interval_s=min_interval_s,
            hourly_limit=hourly_limit,
            daily_limit=daily_limit,
            now_ts=float(now),
        )
        if not ok:
            return False, reason

        # Also enforce account-scoped counters when an account is provided.
        akey = self._account_key(account)
        if akey:
            return self._can_send_for_key(
                recipient,
                account_key=akey,
                min_interval_s=min_interval_s,
                hourly_limit=hourly_limit,
                daily_limit=daily_limit,
                now_ts=float(now),
            )

        return True, "OK"

    def _record_sent_for_key(
        self,
        recipient: str,
        *,
        account_key: str,
        now_ts: float,
    ) -> RecipientSendState:
        now = float(now_ts)
        recipient_key = self._normalize_key(recipient)
        akey = self._account_key(account_key)
        day_start = self._day_start_ts(now)

        with self._lock:
            row = self._read_row(recipient_key, akey)
            if row:
                _recipient, _account, _last_sent, hour_start, hour_count, stored_day_start, day_count = row
            else:
                _last_sent = None
                hour_start = now
                hour_count = 0
                stored_day_start = day_start
                day_count = 0

            if now - float(hour_start) >= 3600:
                hour_start = now
                hour_count = 0

            if float(stored_day_start) != float(day_start):
                stored_day_start = day_start
                day_count = 0

            hour_count = int(hour_count) + 1
            day_count = int(day_count) + 1

            self._conn.execute(
                """
                INSERT INTO recipient_counters (
                    recipient, account, last_sent_ts,
                    hour_window_start_ts, hour_count,
                    day_window_start_ts, day_count,
                    updated_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recipient, account) DO UPDATE SET
                    last_sent_ts=excluded.last_sent_ts,
                    hour_window_start_ts=excluded.hour_window_start_ts,
                    hour_count=excluded.hour_count,
                    day_window_start_ts=excluded.day_window_start_ts,
                    day_count=excluded.day_count,
                    updated_ts=excluded.updated_ts
                """,
                (
                    recipient_key,
                    akey,
                    float(now),
                    float(hour_start),
                    int(hour_count),
                    float(stored_day_start),
                    int(day_count),
                    float(now),
                ),
            )
            self._conn.commit()

        return RecipientSendState(
            recipient=recipient_key,
            account=akey,
            last_sent_ts=float(now),
            hour_window_start_ts=float(hour_start),
            hour_count=int(hour_count),
            day_window_start_ts=float(stored_day_start),
            day_count=int(day_count),
        )

    def record_sent(
        self,
        recipient: str,
        *,
        account: Optional[str] = None,
        now_ts: Optional[float] = None,
    ) -> RecipientSendState:
        now = float(now_ts if now_ts is not None else time.time())

        # Always update global counters first (cross-account).
        global_state = self._record_sent_for_key(
            recipient,
            account_key=self.GLOBAL_ACCOUNT_KEY,
            now_ts=now,
        )

        # Also update per-account counters when an account is provided.
        akey = self._account_key(account)
        if akey:
            return self._record_sent_for_key(recipient, account_key=akey, now_ts=now)

        return global_state
