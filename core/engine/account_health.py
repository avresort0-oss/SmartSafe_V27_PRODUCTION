from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional
from collections import deque


AUTO_ROTATE_ACCOUNT_SENTINEL = "__auto_rotate__"


@dataclass
class QuarantineState:
    quarantined_until_ts: float = 0.0
    reason: str = ""

    def is_quarantined(self, now_ts: Optional[float] = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        return self.quarantined_until_ts > now

    def remaining_s(self, now_ts: Optional[float] = None) -> int:
        now = time.time() if now_ts is None else float(now_ts)
        return max(0, int(self.quarantined_until_ts - now))


@dataclass
class AccountHealthState:
    # Raw counters (since process start)
    sent_ok: int = 0
    sent_failed: int = 0
    retried: int = 0

    # Connection tracking (from Node /stats and/or inferred failures)
    last_connected: Optional[bool] = None
    disconnect_events_recent: Deque[float] = field(default_factory=lambda: deque(maxlen=50))

    # Error tracking
    consecutive_failures: int = 0
    last_error: str = ""
    recent_errors: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=50))

    # Smoothed signals
    ema_error_rate: float = 0.0
    last_update_ts: float = 0.0

    quarantine: QuarantineState = field(default_factory=QuarantineState)


@dataclass
class AccountHealthConfig:
    """
    Heuristic configuration for health scoring and quarantine triggers.

    Score semantics: 0 (worst) .. 100 (best).
    """

    # EMA smoothing for per-message failures: higher alpha reacts faster
    ema_alpha: float = 0.20

    # Quarantine triggers
    quarantine_score_threshold: int = 35
    quarantine_consecutive_failures: int = 5

    # Quarantine durations
    quarantine_default_s: int = 30 * 60
    quarantine_disconnect_s: int = 45 * 60
    quarantine_critical_error_s: int = 12 * 60 * 60

    # Rotation gates
    min_score_to_use: int = 40
    disconnect_window_s: int = 30 * 60
    error_window_s: int = 10 * 60


class AccountHealthTracker:
    """
    In-memory per-account health tracker with auto-quarantine support.

    Designed to be cheap to update from the engine hot-path (per message) and
    safe to call from multiple threads.
    """

    def __init__(self, config: Optional[AccountHealthConfig] = None) -> None:
        self.config = config or AccountHealthConfig()
        self._lock = threading.Lock()
        self._accounts: Dict[str, AccountHealthState] = {}

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------
    def get_state(self, account: str) -> AccountHealthState:
        key = (account or "").strip()
        if not key:
            key = "default"
        with self._lock:
            if key not in self._accounts:
                self._accounts[key] = AccountHealthState(last_update_ts=time.time())
            return self._accounts[key]

    def is_quarantined(self, account: str, now_ts: Optional[float] = None) -> bool:
        st = self.get_state(account)
        return st.quarantine.is_quarantined(now_ts=now_ts)

    def quarantine(self, account: str, *, reason: str, duration_s: int) -> None:
        st = self.get_state(account)
        now = time.time()
        until = now + max(1, int(duration_s))
        with self._lock:
            st.quarantine.quarantined_until_ts = max(st.quarantine.quarantined_until_ts, until)
            st.quarantine.reason = reason or st.quarantine.reason or "quarantined"
            st.last_update_ts = now

    def unquarantine(self, account: str) -> None:
        st = self.get_state(account)
        with self._lock:
            st.quarantine = QuarantineState()
            st.last_update_ts = time.time()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for account, st in self._accounts.items():
                out[account] = self._state_to_view(account, st, now_ts=now)
            return out

    # ------------------------------------------------------------------
    # Updates from engine / node stats
    # ------------------------------------------------------------------
    def record_retry(self, account: str) -> None:
        st = self.get_state(account)
        with self._lock:
            st.retried += 1
            st.last_update_ts = time.time()

    def record_message_result(
        self,
        account: str,
        *,
        success: bool,
        error: Optional[str] = None,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        retryable: Optional[bool] = None,
        risk_score: Optional[int] = None,
        now_ts: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Record a single send outcome.

        Returns an optional action dict when the tracker wants to quarantine:
            {"action": "quarantine", "account": str, "duration_s": int, "reason": str}
        """
        now = time.time() if now_ts is None else float(now_ts)
        st = self.get_state(account)
        err_txt = (error or "").strip()
        code_txt = (code or "").strip()

        # Update EMA and counters
        sample_err = 0.0 if success else 1.0
        with self._lock:
            st.ema_error_rate = (self.config.ema_alpha * sample_err) + ((1.0 - self.config.ema_alpha) * st.ema_error_rate)
            if success:
                st.sent_ok += 1
                st.consecutive_failures = 0
            else:
                st.sent_failed += 1
                st.consecutive_failures += 1
                st.last_error = err_txt or code_txt or st.last_error
                st.recent_errors.append(
                    {
                        "ts": now,
                        "error": err_txt or None,
                        "code": code_txt or None,
                        "status_code": int(status_code or 0),
                        "retryable": bool(retryable) if retryable is not None else None,
                        "risk_score": int(risk_score) if risk_score is not None else None,
                    }
                )
            st.last_update_ts = now

        # Critical error keywords: quarantine aggressively.
        if self._is_critical_error(err_txt, code_txt):
            duration_s = int(self.config.quarantine_critical_error_s)
            reason = f"critical_error: {code_txt or err_txt}".strip()
            self.quarantine(account, reason=reason, duration_s=duration_s)
            return {"action": "quarantine", "account": account, "duration_s": duration_s, "reason": reason}

        # Heuristic quarantine triggers
        score = self.score(account, now_ts=now)
        if st.consecutive_failures >= self.config.quarantine_consecutive_failures:
            duration_s = int(self.config.quarantine_default_s)
            reason = f"consecutive_failures={st.consecutive_failures}"
            self.quarantine(account, reason=reason, duration_s=duration_s)
            return {"action": "quarantine", "account": account, "duration_s": duration_s, "reason": reason}

        if score <= int(self.config.quarantine_score_threshold):
            duration_s = int(self.config.quarantine_default_s)
            reason = f"low_health_score={score}"
            self.quarantine(account, reason=reason, duration_s=duration_s)
            return {"action": "quarantine", "account": account, "duration_s": duration_s, "reason": reason}

        return None

    def sync_node_account_row(self, account: str, row: Dict[str, Any], *, now_ts: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Incorporate Node `/stats` signals like `connected`, `errors`, `last_error`.

        Returns an optional quarantine action dict (same shape as `record_message_result`).
        """
        now = time.time() if now_ts is None else float(now_ts)
        st = self.get_state(account)
        connected = bool(row.get("connected"))
        last_error = str(row.get("last_error") or "").strip()

        action: Optional[Dict[str, Any]] = None
        with self._lock:
            prev = st.last_connected
            st.last_connected = connected
            if prev is True and connected is False:
                st.disconnect_events_recent.append(now)
            if last_error:
                st.last_error = last_error
            st.last_update_ts = now

        # If disconnected + recent failures, quarantine.
        if not connected:
            recent_disc = self._count_recent(st.disconnect_events_recent, window_s=self.config.disconnect_window_s, now_ts=now)
            if recent_disc >= 1 and st.consecutive_failures >= 3:
                duration_s = int(self.config.quarantine_disconnect_s)
                reason = f"disconnected+failures ({st.consecutive_failures})"
                self.quarantine(account, reason=reason, duration_s=duration_s)
                action = {"action": "quarantine", "account": account, "duration_s": duration_s, "reason": reason}

        if self._is_critical_error(last_error, ""):
            duration_s = int(self.config.quarantine_critical_error_s)
            reason = f"critical_error: {last_error}"
            self.quarantine(account, reason=reason, duration_s=duration_s)
            action = {"action": "quarantine", "account": account, "duration_s": duration_s, "reason": reason}

        return action

    # ------------------------------------------------------------------
    # Scoring / routing helpers
    # ------------------------------------------------------------------
    def score(self, account: str, *, now_ts: Optional[float] = None) -> int:
        now = time.time() if now_ts is None else float(now_ts)
        st = self.get_state(account)

        with self._lock:
            ema = float(st.ema_error_rate)
            consecutive = int(st.consecutive_failures)
            connected = st.last_connected
            recent_disc = self._count_recent(st.disconnect_events_recent, window_s=self.config.disconnect_window_s, now_ts=now)
            recent_err = self._count_recent_errors(st, window_s=self.config.error_window_s, now_ts=now)

        # Base score starts at 100 and subtracts penalties.
        score = 100
        # Error-rate EMA is the main signal.
        score -= int(min(60, ema * 60.0))
        # Consecutive failures penalize quickly.
        score -= min(25, consecutive * 5)
        # Connection instability is high risk.
        score -= min(30, recent_disc * 15)
        # Many recent errors = degrade
        score -= min(20, recent_err * 4)
        if connected is False:
            score -= 20

        return max(0, min(100, int(score)))

    def can_use_for_send(self, account: str, *, now_ts: Optional[float] = None) -> tuple[bool, str]:
        now = time.time() if now_ts is None else float(now_ts)
        st = self.get_state(account)
        if st.quarantine.is_quarantined(now_ts=now):
            return False, f"quarantined ({st.quarantine.remaining_s(now_ts=now)}s left): {st.quarantine.reason or 'risk'}"
        score = self.score(account, now_ts=now)
        if score < int(self.config.min_score_to_use):
            return False, f"health_score_too_low={score}"
        if st.last_connected is False:
            return False, "disconnected"
        return True, "OK"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _state_to_view(self, account: str, st: AccountHealthState, *, now_ts: float) -> Dict[str, Any]:
        return {
            "account": account,
            "score": self.score(account, now_ts=now_ts),
            "sent_ok": st.sent_ok,
            "sent_failed": st.sent_failed,
            "retried": st.retried,
            "ema_error_rate": round(float(st.ema_error_rate), 4),
            "consecutive_failures": st.consecutive_failures,
            "connected": st.last_connected,
            "last_error": st.last_error,
            "quarantined": st.quarantine.is_quarantined(now_ts=now_ts),
            "quarantine_remaining_s": st.quarantine.remaining_s(now_ts=now_ts),
            "quarantine_reason": st.quarantine.reason,
            "last_update_ts": st.last_update_ts,
        }

    @staticmethod
    def _count_recent(ts_list: Deque[float], *, window_s: int, now_ts: float) -> int:
        if not ts_list:
            return 0
        cutoff = now_ts - float(window_s)
        return sum(1 for t in ts_list if float(t) >= cutoff)

    @staticmethod
    def _count_recent_errors(st: AccountHealthState, *, window_s: int, now_ts: float) -> int:
        if not st.recent_errors:
            return 0
        cutoff = now_ts - float(window_s)
        return sum(1 for e in st.recent_errors if float(e.get("ts", 0.0)) >= cutoff)

    @staticmethod
    def _is_critical_error(error_text: str, code_text: str) -> bool:
        blob = f"{code_text} {error_text}".lower()
        # Conservative: quarantine on strong signals only.
        keywords = [
            "banned",
            "ban",
            "logged out",
            "logout",
            "not authorized",
            "unauthorized",
            "401",
            "forbidden",
            "403",
            "session invalid",
            "conflict",
            "device removed",
            "account removed",
        ]
        return any(k in blob for k in keywords)
