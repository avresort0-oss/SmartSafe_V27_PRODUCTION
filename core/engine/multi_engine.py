"""
SmartSafe V27 - Advanced Multi-Instance Bulk Messaging Engine
Production-ready with threading, queue management, and comprehensive error handling.
"""

from __future__ import annotations

import logging
import zlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from queue import Empty, Queue
from typing import Callable, Dict, List, Optional

from core.api.whatsapp_baileys import BaileysAPI
from core.config import SETTINGS
from core.engine.risk_brain import RiskBrain, RiskMode
from core.engine.account_health import AUTO_ROTATE_ACCOUNT_SENTINEL, AccountHealthTracker
from core.engine.spam_detection_engine import SpamDetectionEngine
class EngineProfile(Enum):
    SAFE = "safe"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

logger = logging.getLogger(__name__)


class EngineStatus(Enum):
    """Engine status states."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class MessageTask:
    """Message task data structure."""

    contact: Dict
    message_template: str
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class MessageResult:
    """Message result data structure."""

    contact: Dict
    success: bool
    message: str
    timestamp: datetime
    error: Optional[str] = None


class MultiEngine:
    """Queue-based bulk sender with risk-aware pacing and retries."""

    def __init__(
        self,
        api_host: str = SETTINGS.api_host,
        mode: RiskMode = RiskMode.SAFE,
        max_workers: int = 1,
        enable_retry: bool = True,
    ):
        self.api = BaileysAPI(api_host)
        self.risk_brain = RiskBrain(mode=mode)
        self.spam_engine = SpamDetectionEngine()

        self.status = EngineStatus.IDLE
        self.is_running = False
        self.is_paused = False

        self.max_workers = max(1, int(max_workers))
        self.worker_threads: List[threading.Thread] = []
        self.result_processor_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.completion_event = threading.Event()
        self._finalized = False

        self.task_queue: Queue[MessageTask] = Queue()
        self.result_queue: Queue[MessageResult] = Queue()
        self.pending_tasks: List[MessageTask] = []
        self.completed_tasks: List[MessageResult] = []
        self.failed_tasks: List[MessageResult] = []

        self.enable_retry = enable_retry
        self.retry_delay = 10

        self.stats = {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "pending": 0,
            "retried": 0,
            "start_time": None,
            "end_time": None,
            "elapsed_time": 0,
        }

        self.status_callback: Optional[Callable[[str], None]] = None
        self.progress_callback: Optional[Callable[[int, int], None]] = None
        self.completion_callback: Optional[Callable[[Dict], None]] = None

        # Lightweight account rotation cache (for AUTO_ROTATE routing)
        self._rotation_accounts: List[str] = []
        self._rotation_account_stats: Dict[str, Dict] = {}
        self._rotation_index: int = 0
        self._last_accounts_refresh: float = 0.0
        self._accounts_refresh_interval: float = 30.0

        # Health tracking (used for smarter auto-rotation decisions)
        self.account_health = AccountHealthTracker()

        logger.info("MultiEngine initialized: mode=%s workers=%s", mode.value, self.max_workers)

    # ------------------------------------------------------------------
    # Account routing helpers
    # ------------------------------------------------------------------
    def _refresh_accounts_cache(self, force: bool = False) -> None:
        now = time.time()
        if not force and self._rotation_accounts and (now - self._last_accounts_refresh) < self._accounts_refresh_interval:
            return

        accounts: List[str] = []
        try:
            stats_resp = self.api.get_stats()
            if stats_resp.get("ok"):
                stats = stats_resp.get("stats", {}) or {}
                self._rotation_account_stats = stats
                for acc, row in stats.items():
                    try:
                        self.account_health.sync_node_account_row(acc, row)
                    except Exception:
                        pass
                connected = [acc for acc, row in stats.items() if row.get("connected")]
                if connected:
                    accounts = connected
        except Exception:
            accounts = []

        if not accounts:
            try:
                acc_resp = self.api.get_accounts()
                if acc_resp.get("ok"):
                    for item in acc_resp.get("accounts", []) or []:
                        name = item.get("account") or item.get("name")
                        if name:
                            accounts.append(str(name))
            except Exception:
                accounts = []

        if not accounts:
            accounts = ["default"]

        # Prefer accounts that are usable per health tracker
        try:
            usable = []
            for acc in accounts:
                ok, _reason = self.account_health.can_use_for_send(acc)
                if ok:
                    usable.append(acc)
            if usable:
                accounts = usable
        except Exception:
            pass

        # Sort by health score (desc) to bias rotation toward healthier accounts.
        try:
            snapshot = self.account_health.snapshot()
            accounts.sort(key=lambda acc: int(snapshot.get(acc, {}).get("score", 0) or 0), reverse=True)
        except Exception:
            pass

        self._rotation_accounts = accounts
        if self._rotation_index >= len(accounts):
            self._rotation_index = 0
        self._last_accounts_refresh = now

    def _next_rotation_account(self) -> str:
        self._refresh_accounts_cache()
        if not self._rotation_accounts:
            return "default"
        account = self._rotation_accounts[self._rotation_index % len(self._rotation_accounts)]
        self._rotation_index = (self._rotation_index + 1) % len(self._rotation_accounts)
        return account

    def send_bulk(
        self,
        contacts: List[Dict],
        message_template: str,
        callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        completion_callback: Optional[Callable[[Dict], None]] = None,
        *,
        profile: Optional[EngineProfile] = None,
        profile_name: Optional[str] = None,
        metadata: Optional[Dict] = None,
        **_ignored,
    ) -> Dict:
        if not contacts:
            return {"ok": False, "error": "No contacts provided"}
        if not message_template:
            return {"ok": False, "error": "No message template provided"}
        if self.is_running:
            return {"ok": False, "error": "Engine already running"}

        # Apply optional profile selection to the RiskBrain (best-effort).
        profile_key = ""
        if profile is not None:
            profile_key = str(profile.value or "").lower()
        elif profile_name:
            profile_key = str(profile_name).lower()

        profile_to_mode = {
            "safe": RiskMode.SAFE,
            "balanced": RiskMode.FAST,
            "aggressive": RiskMode.TURBO,
        }
        if profile_key in profile_to_mode:
            try:
                self.risk_brain.set_mode(profile_to_mode[profile_key])
            except Exception:
                pass

        # Metadata is currently informational only; kept for UI compatibility.
        _ = metadata

        self.status_callback = callback
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback

        self._reset_state()
        self.is_running = True
        self.is_paused = False
        self.status = EngineStatus.RUNNING

        self.stats["total"] = len(contacts)
        self.stats["start_time"] = datetime.now()

        # Refresh account rotation list for this run
        self._refresh_accounts_cache(force=True)

        for contact in contacts:
            task = MessageTask(contact=contact, message_template=message_template)
            self.pending_tasks.append(task)
            self.task_queue.put(task)

        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_thread, name=f"Worker-{i + 1}", daemon=True)
            worker.start()
            self.worker_threads.append(worker)

        self.result_processor_thread = threading.Thread(
            target=self._result_processor_thread,
            name="ResultProcessor",
            daemon=True,
        )
        self.result_processor_thread.start()

        return {"ok": True, "total": self.stats["total"], "mode": self.risk_brain.mode.value}

    def _worker_thread(self) -> None:
        thread_name = threading.current_thread().name
        logger.info("%s started", thread_name)

        while self.is_running:
            try:
                while self.is_paused and self.is_running:
                    time.sleep(0.2)

                if not self.is_running:
                    break

                try:
                    task = self.task_queue.get(timeout=0.5)
                except Empty:
                    continue

                try:
                    result = self._process_task(task)
                except Exception as exc:
                    logger.error("Task processing error: %s", exc, exc_info=True)
                    result = MessageResult(
                        contact=task.contact,
                        success=False,
                        message="Processing error",
                        timestamp=datetime.now(),
                        error=str(exc),
                    )

                self.result_queue.put(result)
                self.task_queue.task_done()

            except Exception as exc:
                logger.error("Worker thread error: %s", exc, exc_info=True)

        logger.info("%s stopped", thread_name)

    def _process_task(self, task: MessageTask) -> MessageResult:
        contact = task.contact
        number = contact.get("phone", "")
        name = contact.get("name", "User")
        raw_account = contact.get("account")
        if raw_account == AUTO_ROTATE_ACCOUNT_SENTINEL:
            account = self._next_rotation_account()
        elif isinstance(raw_account, str) and raw_account.strip():
            account = raw_account.strip()
        else:
            account = "default"

        # Smart Anti-Ban: Full risk check with proxy/read receipts
        can_send, reason, anti_ban_settings = self.risk_brain.can_send_message(
            number, account=account
        )
        proxy = anti_ban_settings.get('proxy')
        read_receipts = anti_ban_settings.get('read_receipts', True)
        
        if not can_send:
            if self.status_callback:
                self.status_callback(f"Anti-Ban paused: {reason}")

            if "limit" in reason.lower():
                time.sleep(60)
            else:
                time.sleep(10)

            if self.enable_retry and task.retry_count < task.max_retries:
                task.retry_count += 1
                self.task_queue.put(task)
                with self.lock:
                    self.stats["retried"] += 1
                try:
                    self.account_health.record_retry(account)
                except Exception:
                    pass
                return MessageResult(
                    contact=contact,
                    success=False,
                    message="Requeued (Anti-Ban)",
                    timestamp=datetime.now(),
                    error=reason,
                )

            return MessageResult(
                contact=contact,
                success=False,
                message="Blocked by Anti-Ban",
                timestamp=datetime.now(),
                error=reason,
            )

        should_pause, pause_reason = self.risk_brain.should_pause()
        if should_pause:
            if self.status_callback:
                self.status_callback(f"High risk. Pausing: {pause_reason}")
            time.sleep(60)

        message = self._prepare_message(task.message_template, contact)

        spam_result = self.spam_engine.process_message({'content': message})
        if spam_result['is_spam']:
            if self.status_callback:
                self.status_callback(f"Spam detected for {name}. Blocking message.")
            return MessageResult(
                contact=contact,
                success=False,
                message="Spam detected",
                timestamp=datetime.now(),
                error="Message was classified as spam.",
            )

        # Calculate smart delay (message_length for typing sim)
        msg_length = len(message)
        delay = self.risk_brain.get_safe_delay(msg_length, randomize=True)
        time.sleep(delay)
        
        try:
            # Anti-Ban send with proxy/read_receipts
            result = self.api.send_message(
                number, 
                message, 
                account=account,
                proxy=proxy,
                read_receipts=read_receipts
            )
            if result.get("ok"):
                self.risk_brain.record_message(number, account=account)
                try:
                    self.risk_brain.record_outgoing_content(message, account=account)
                except Exception:
                    pass
                try:
                    self.account_health.record_message_result(account, success=True)
                except Exception:
                    pass
                if self.status_callback:
                    self.status_callback(f"✅ Sent to {name} via proxy:{bool(proxy)}")
                return MessageResult(
                    contact=contact,
                    success=True,
                    message=f"Sent (delay:{delay:.1f}s, proxy:{bool(proxy)})",
                    timestamp=datetime.now(),
                )

            error = result.get("error", "Unknown error")
            if self.status_callback:
                self.status_callback(f"Failed: {name} - {error}")

            if self.enable_retry and task.retry_count < task.max_retries:
                task.retry_count += 1
                time.sleep(self.retry_delay)
                self.task_queue.put(task)
                with self.lock:
                    self.stats["retried"] += 1
                try:
                    self.account_health.record_message_result(
                        account,
                        success=False,
                        error=error,
                        code=result.get("code"),
                        status_code=result.get("status_code"),
                        retryable=result.get("retryable"),
                    )
                    self.account_health.record_retry(account)
                except Exception:
                    pass
                return MessageResult(
                    contact=contact,
                    success=False,
                    message="Retrying",
                    timestamp=datetime.now(),
                    error=error,
                )

            try:
                self.account_health.record_message_result(
                    account,
                    success=False,
                    error=error,
                    code=result.get("code"),
                    status_code=result.get("status_code"),
                    retryable=result.get("retryable"),
                )
            except Exception:
                pass

            return MessageResult(
                contact=contact,
                success=False,
                message="Send failed",
                timestamp=datetime.now(),
                error=error,
            )

        except Exception as exc:
            logger.error("Exception sending to %s: %s", name, exc, exc_info=True)
            if self.status_callback:
                self.status_callback(f"Error: {name} - {exc}")
            try:
                self.account_health.record_message_result(account, success=False, error=str(exc))
            except Exception:
                pass
            return MessageResult(
                contact=contact,
                success=False,
                message="Exception",
                timestamp=datetime.now(),
                error=str(exc),
            )

    def _result_processor_thread(self) -> None:
        logger.info("Result processor started")
        while True:
            result: Optional[MessageResult] = None
            try:
                try:
                    result = self.result_queue.get(timeout=0.5)
                except Empty:
                    result = None

                if result is not None:
                    with self.lock:
                        if result.success:
                            self.stats["sent"] += 1
                            self.completed_tasks.append(result)
                        elif result.message != "Requeued":
                            self.stats["failed"] += 1
                            self.failed_tasks.append(result)

                        self.stats["pending"] = self.stats["total"] - self.stats["sent"] - self.stats["failed"]

                    if self.progress_callback:
                        completed = self.stats["sent"] + self.stats["failed"]
                        self.progress_callback(completed, self.stats["total"])

                    self.result_queue.task_done()

                if self.is_running and self.task_queue.unfinished_tasks == 0 and self.result_queue.empty():
                    self._finalize()

                if (not self.is_running) and self.result_queue.empty():
                    break

            except Exception as exc:
                logger.error("Result processor error: %s", exc, exc_info=True)

        logger.info("Result processor stopped")

    def _prepare_message(self, template: str, contact: Dict) -> str:
        message = template
        for key, value in contact.items():
            message = message.replace(f"{{{key}}}", str(value))
        return message

    def _finalize(self) -> None:
        with self.lock:
            if self._finalized:
                return
            self._finalized = True

        self.is_running = False
        self.status = EngineStatus.IDLE
        self.stats["end_time"] = datetime.now()

        if self.stats["start_time"]:
            elapsed = self.stats["end_time"] - self.stats["start_time"]
            self.stats["elapsed_time"] = elapsed.total_seconds()

        logger.info("Bulk send completed")
        logger.info("Stats: %s", self.stats)

        if self.completion_callback:
            self.completion_callback(self.get_stats())

        if self.status_callback:
            self.status_callback(f"Completed: {self.stats['sent']} sent, {self.stats['failed']} failed")

        self.completion_event.set()

    def _reset_state(self) -> None:
        self.pending_tasks.clear()
        self.completed_tasks.clear()
        self.failed_tasks.clear()
        self.worker_threads.clear()
        self.result_processor_thread = None
        self.completion_event.clear()
        self._finalized = False

        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except Empty:
                break

        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
                self.result_queue.task_done()
            except Empty:
                break

        self.stats = {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "pending": 0,
            "retried": 0,
            "start_time": None,
            "end_time": None,
            "elapsed_time": 0,
        }

    def pause(self) -> None:
        if not self.is_running:
            return
        self.is_paused = True
        self.status = EngineStatus.PAUSED
        if self.status_callback:
            self.status_callback("Paused")

    def resume(self) -> None:
        if not self.is_paused:
            return
        self.is_paused = False
        self.status = EngineStatus.RUNNING
        if self.status_callback:
            self.status_callback("Resumed")

    def stop(self) -> None:
        if not self.is_running and self.status != EngineStatus.PAUSED:
            return

        self.is_running = False
        self.is_paused = False
        self.status = EngineStatus.STOPPED

        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=5)

        if self.result_processor_thread and self.result_processor_thread.is_alive():
            self.result_processor_thread.join(timeout=5)

        self.worker_threads.clear()
        self.result_processor_thread = None
        self.completion_event.set()

        if self.status_callback:
            self.status_callback("Stopped")

    def get_stats(self) -> Dict:
        with self.lock:
            return {
                **self.stats,
                "status": self.status.value,
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "risk_score": self.risk_brain.current_risk_score,
                "risk_recommendation": self.risk_brain.get_recommendation(),
                "success_rate": ((self.stats["sent"] / max(self.stats["total"], 1)) * 100) if self.stats["total"] > 0 else 0,
                "messages_per_minute": ((self.stats["sent"] / max(self.stats["elapsed_time"], 1)) * 60) if self.stats["elapsed_time"] > 0 else 0,
            }

    def get_account_health(self) -> Dict:
        """
        Return per-account health snapshot (used by analytics tabs).
        """
        try:
            return self.account_health.snapshot()
        except Exception:
            return {}

    def get_failed_contacts(self) -> List[Dict]:
        return [result.contact for result in self.failed_tasks]

    def retry_failed(self) -> None:
        if not self.failed_tasks:
            logger.info("No failed tasks to retry")
            return

        template = self.pending_tasks[0].message_template if self.pending_tasks else ""
        for result in self.failed_tasks:
            task = MessageTask(contact=result.contact, message_template=template, retry_count=0)
            self.task_queue.put(task)

        self.failed_tasks.clear()
        logger.info("Queued failed tasks for retry")

    def run_preflight_audit(
        self,
        contacts: List[Dict],
        message_template: str,
        *,
        profile: Optional[EngineProfile] = None,
        profile_name: Optional[str] = None,
    ) -> Dict:
        """
        Run a read-only safety audit on the proposed campaign.
        """
        try:
            # 1. Hygiene Check
            total = len(contacts)
            valid = 0
            seen = set()
            duplicates = 0
            
            for c in contacts:
                phone = c.get("phone") or c.get("number")
                if not phone:
                    continue
                if phone in seen:
                    duplicates += 1
                else:
                    seen.add(phone)
                    valid += 1
            
            invalid = total - valid - duplicates

            # 2. Pacing & Limits (Snapshot from RiskBrain)
            rb_config = self.risk_brain.get_config()
            avg_delay = (rb_config.min_delay + rb_config.max_delay) / 2.0
            est_duration_min = (total * avg_delay) / 60.0
            
            # 3. Current Risk Score
            current_risk = self.risk_brain.calculate_risk()
            
            # 4. CRC32 for freshness check
            msg_crc = zlib.crc32((message_template or "").encode("utf-8")) & 0xFFFFFFFF

            return {
                "ok": True,
                "profile": profile_name or "current",
                "generated_at": datetime.now().isoformat(),
                "contacts": {
                    "rows_total": total,
                    "valid": valid,
                    "invalid": invalid,
                    "duplicates": duplicates,
                    "unique": len(seen)
                },
                "pacing": {
                    "avg_delay_s": round(avg_delay, 1),
                    "estimated_msgs_per_min": round(60.0 / avg_delay, 1) if avg_delay > 0 else 0,
                    "estimated_duration_min": round(est_duration_min, 1),
                    "estimated_duration_hr": round(est_duration_min / 60.0, 1),
                    "minute_limit": rb_config.minute_limit,
                    "hourly_limit": rb_config.hourly_limit,
                    "daily_limit": rb_config.daily_limit,
                },
                "risk": {
                    "score": current_risk,
                    "label": self.risk_brain._get_risk_level().value,
                    "factors": self.risk_brain.risk_factors
                },
                "schedule": {
                    "current_hour": datetime.now().hour,
                    "time_window_risk": "LOW",
                    "in_quiet_hours_now": False 
                },
                "inputs": {
                    "profile_name": profile_name,
                    "message_crc32": msg_crc
                }
            }
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            return {"ok": False, "error": str(e)}
