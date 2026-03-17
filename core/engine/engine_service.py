from __future__ import annotations

import logging
import uuid
from threading import Lock
from typing import Callable, Dict, List, Optional

from core.engine.multi_engine import EngineProfile, MultiEngine

logger = logging.getLogger(__name__)


class EngineService:
    """
    High-level facade around `MultiEngine` for use by UI tabs.

    This service owns a single `MultiEngine` instance and exposes a small,
    UI-friendly API focused on **jobs and job control** instead of low-level
    engine details. It provides the primary **UI ↔ engine** contract:

    - Tabs create and control bulk jobs only through this service.
    - Callers never access `MultiEngine` directly.
    - Job lifecycle methods (`start_bulk_job`, `pause_job`, `resume_job`,
      `stop_job`, `retry_failed`) are safe to call from UI threads and return
      clear booleans/dicts instead of raising on normal flow.

    Contract summary:

    - `start_bulk_job(...) -> Dict`:
        - On success returns `{"ok": True, "job_id": "<id>", ...}`.
        - On failure returns `{"ok": False, "error": "<reason>"}` and does not
          change the active job.
    - `get_job_stats(job_id) -> Optional[Dict]`:
        - Returns a shallow copy of engine stats for that job, or `None` if
          unknown.
    - Control methods (`pause_job`, `resume_job`, `stop_job`, `retry_failed`)
        - Return `True` when the action was applied to the current job, `False`
          otherwise (no exception for stale/unknown job IDs).
    - Snapshot helpers (`get_engine_stats`, `get_failed_contacts`) expose
      read-only views over engine state for dashboards.

    See `ARCHITECTURE.md` for how this service fits between the CustomTkinter
    tabs and the underlying engine/Node/Baileys layers.
    """

    def __init__(self, engine: Optional[MultiEngine] = None) -> None:
        self._engine: MultiEngine = engine or MultiEngine()
        self._lock = Lock()
        self._active_job_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------
    def start_bulk_job(
        self,
        contacts: List[Dict],
        message_template: str,
        *,
        profile: Optional[EngineProfile] = None,
        profile_name: Optional[str] = None,
        metadata: Optional[Dict] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        completion_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """
        Start a new bulk job and return the underlying engine response.

        The returned dict always contains a `job_id` key when `ok` is True.
        UI tabs are expected to use this `job_id` for subsequent calls.
        """
        logger.info("Starting bulk job via EngineService")

        result = self._engine.send_bulk(
            contacts=contacts,
            message_template=message_template,
            callback=status_callback,
            progress_callback=progress_callback,
            completion_callback=completion_callback,
            profile=profile,
            profile_name=profile_name,
            metadata=metadata,
        )

        job_id = result.get("job_id")
        if result.get("ok"):
            # Ensure a job_id is always present so UI controls can target the run.
            if not job_id:
                job_id = f"job_{uuid.uuid4().hex[:8]}"
                result["job_id"] = job_id
            with self._lock:
                self._active_job_id = job_id
        else:
            logger.warning("Failed to start bulk job via EngineService: %s", result)

        return result

    def get_job_stats(self, job_id: str) -> Optional[Dict]:
        """
        Get stats for a specific job.
        """
        return self._engine.get_job_stats(job_id)

    def get_all_job_stats(self) -> List[Dict]:
        """
        Get summaries for all known jobs.
        """
        return self._engine.list_jobs()

    # ------------------------------------------------------------------
    # Job control
    # ------------------------------------------------------------------
    def pause_job(self, job_id: Optional[str] = None) -> bool:
        """
        Pause the active job.

        If `job_id` is provided, it must match the currently active job in order
        for the pause to be applied. Returns True when a pause was triggered.
        """
        if not self._is_current_job(job_id):
            return False

        self._engine.pause()
        return True

    def resume_job(self, job_id: Optional[str] = None) -> bool:
        """
        Resume the active job if it is currently paused.
        """
        if not self._is_current_job(job_id):
            return False

        self._engine.resume()
        return True

    def stop_job(self, job_id: Optional[str] = None) -> bool:
        """
        Stop the active job.
        """
        if not self._is_current_job(job_id):
            return False

        self._engine.stop()
        return True

    def retry_failed(self, job_id: Optional[str] = None) -> bool:
        """
        Retry failed contacts for the active job.

        This delegates to the underlying engine's `retry_failed` method, which
        acts on the current job only.
        """
        if not self._is_current_job(job_id):
            return False

        self._engine.retry_failed()
        return True

    def get_active_job_id(self) -> Optional[str]:
        """
        Return the job ID of the most recently started (and still tracked) job.
        """
        with self._lock:
            return self._active_job_id

    def get_engine_stats(self) -> Dict:
        """
        Convenience wrapper over `MultiEngine.get_stats` for UI consumers.
        """
        return self._engine.get_stats()

    def get_failed_contacts(self) -> List[Dict]:
        """
        Return failed contacts for the current or most recent job.
        """
        return self._engine.get_failed_contacts()

    # ------------------------------------------------------------------
    # Phase C: Compliance (DNC / opt-out helpers)
    # ------------------------------------------------------------------

    def add_to_dnc(
        self,
        number: str,
        *,
        reason: str = "manual",
        source: str = "manual",
        message_text: Optional[str] = None,
    ) -> Dict:
        """
        Add a number to the persistent DNC registry (when enabled).
        """
        if not hasattr(self._engine, "register_opt_out"):
            return {"ok": False, "error": "Engine does not support DNC registry"}
        return self._engine.register_opt_out(number, message_text=message_text, source=source, reason=reason)

    def ingest_inbound_message(self, from_number: str, text: Optional[str], *, source: str = "incoming") -> Dict:
        """
        Convenience wrapper to detect opt-out keywords and register DNC entries.
        """
        if not hasattr(self._engine, "ingest_inbound_message"):
            return {"ok": False, "error": "Engine does not support inbound ingestion"}
        return self._engine.ingest_inbound_message(from_number, text, source=source)

    # ------------------------------------------------------------------
    # Preflight safety audit
    # ------------------------------------------------------------------
    def run_preflight_audit(
        self,
        contacts: List[Dict],
        message_template: str,
        *,
        profile: Optional[EngineProfile] = None,
        profile_name: Optional[str] = None,
    ) -> Dict:
        """
        Run a read-only campaign safety audit (no job creation).
        """
        return self._engine.run_preflight_audit(
            contacts=contacts,
            message_template=message_template,
            profile=profile,
            profile_name=profile_name,
        )

    # ------------------------------------------------------------------
    # Engine configuration
    # ------------------------------------------------------------------
    def configure_engine(
        self,
        profile: Optional[EngineProfile] = None,
        profile_name: Optional[str] = None,
        **overrides,
    ) -> None:
        """
        Configure the underlying engine when no job is running.
        """
        self._engine.configure(profile=profile, profile_name=profile_name, **overrides)

    # ------------------------------------------------------------------
    # Scheduler configuration (quiet hours / ramp-up / random breaks)
    # ------------------------------------------------------------------

    def set_quiet_hours(self, start_hour: int, end_hour: int, *, enabled: bool = True) -> None:
        """
        Configure engine quiet hours (local time).
        """
        self._engine.set_quiet_hours(start_hour, end_hour, enabled=enabled)

    def set_ramp_up(
        self,
        *,
        enabled: bool = True,
        duration_s: int = 20 * 60,
        start_multiplier: float = 2.0,
    ) -> None:
        """
        Configure per-account/day ramp-up pacing.
        """
        self._engine.set_ramp_up(enabled=enabled, duration_s=duration_s, start_multiplier=start_multiplier)

    def set_random_breaks(
        self,
        *,
        enabled: bool = True,
        every_min: int = 12,
        every_max: int = 25,
        duration_min_s: int = 60,
        duration_max_s: int = 4 * 60,
        seed: Optional[int] = None,
    ) -> None:
        """
        Configure per-account/day random breaks.
        """
        self._engine.set_random_breaks(
            enabled=enabled,
            every_min=every_min,
            every_max=every_max,
            duration_min_s=duration_min_s,
            duration_max_s=duration_max_s,
            seed=seed,
        )

    # ------------------------------------------------------------------
    # Account health / quarantine
    # ------------------------------------------------------------------

    def get_account_health(self) -> Dict:
        """
        Return per-account health snapshots derived from engine-side outcomes
        and best-effort Node `/stats` signals.
        """
        return self._engine.get_account_health()

    def quarantine_account(self, account: str, *, reason: str = "manual", duration_s: int = 30 * 60) -> None:
        self._engine.quarantine_account(account, reason=reason, duration_s=duration_s)

    def unquarantine_account(self, account: str) -> None:
        self._engine.unquarantine_account(account)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _is_current_job(self, job_id: Optional[str]) -> bool:
        if job_id is None:
            # When no job_id is supplied, operate on whatever the engine considers
            # its current job.
            return True

        with self._lock:
            is_current = job_id == self._active_job_id

        if not is_current:
            logger.warning("EngineService received control request for unknown job_id=%s", job_id)
        return is_current


_default_service: Optional[EngineService] = None


def get_engine_service() -> EngineService:
    """
    Return a process-wide default `EngineService` instance.

    Tabs can import and use this helper to share the same engine:

        from core.engine.engine_service import get_engine_service
        engine_service = get_engine_service()
    """
    global _default_service
    if _default_service is None:
        _default_service = EngineService()
    return _default_service
