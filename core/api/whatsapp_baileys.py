"""
SmartSafe V27 - Enhanced WhatsApp Baileys API Wrapper
Facade over the shared NodeService client with consistent error handling.
Updated to work with WhiskeySockets/Baileys for full, error-free operation.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from core.api.node_service import NodeService
from core.config import SETTINGS
from core.utils.contacts import normalize_phone

logger = logging.getLogger(__name__)


class BaileysAPI(NodeService):
    """
    High-level WhatsApp API facade built on top of `NodeService`.

    This preserves the existing Baileys-style interface (used across the engine
    and UI tabs) while delegating all HTTP transport and error normalization to
    the unified `NodeService` client. Callers see a consistent payload shape:
    `ok`, `error`, `code`, `status_code`, and `retryable`.
    """

    def __init__(self, host: Optional[str] = None, timeout: Optional[int] = None):
        base_url = (host or SETTINGS.api_host).rstrip("/")
        effective_timeout = int(timeout if timeout is not None else SETTINGS.api_timeout)

        super().__init__(base_url=base_url, timeout=effective_timeout, api_key=SETTINGS.api_key or None)

        self.timeout = effective_timeout
        self.lock = Lock()

        # Lightweight connection statistics for compatibility with existing
        # helpers. Transport-level metrics are exposed by the Node server via
        # `/stats`.
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "last_request_time": None,
            "last_success_time": None,
            "connection_healthy": False,
        }

        # User-agent / defaults for Node server observability.
        self.session.headers.update(
            {
                "Connection": "keep-alive",
                "User-Agent": "SmartSafe-V27/1.1",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        self.health_check_interval = 60  # seconds
        self.last_health_check = 0.0

        logger.info("BaileysAPI initialized: %s", self.base_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _media_path_to_data_url(self, media_path: str) -> Dict[str, Any]:
        path = Path(media_path)
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": f"Media file not found: {media_path}"}

        try:
            content = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            encoded = base64.b64encode(content).decode("ascii")
            return {"ok": True, "data_url": f"data:{mime};base64,{encoded}"}
        except Exception as exc:
            return {"ok": False, "error": f"Failed to encode media file: {exc}"}

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------
    def health_check(self) -> Tuple[bool, str]:
        """
        Cached health helper used by several tabs.
        """
        import time
        from datetime import datetime

        current_time = time.time()
        if current_time - self.last_health_check < self.health_check_interval:
            return self.stats["connection_healthy"], "Cached health status"

        self.last_health_check = current_time
        result = self.get_health()
        if result.get("ok"):
            with self.lock:
                self.stats["connection_healthy"] = True
                self.stats["last_success_time"] = datetime.now()
            return True, "Server healthy"

        with self.lock:
            self.stats["connection_healthy"] = False
        return False, str(result.get("error", "Server unhealthy"))

    def ping(self) -> bool:
        """
        Lightweight liveness probe based on `/health`.
        """
        try:
            result = self.get_health()
            return bool(result.get("ok"))
        except Exception:
            return False

    def get_health(self, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Health/status helper.

        - When account is None: hits `/health` for generic server health.
        - When account is provided: queries `/status` for that account.
        """
        if account:
            return super().get_status(account=account)
        return super().get_health()

    def get_accounts_status(self) -> Dict[str, Any]:
        return super().get_accounts_status()

    def get_qr(self, account: Optional[str] = None) -> Dict[str, Any]:
        return super().get_qr(account)

    def reset_account(self, account: str) -> Dict[str, Any]:
        account = (account or "").strip().lower()
        return super().reset_account(account)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------
    def send_message(
        self,
        number: str,
        message: str,
        media_url: Optional[str] = None,
        media_path: Optional[str] = None,
        account: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced send helper with improved media support and message tracking.

        Args:
            number: Phone number (e.g., "966500000000")
            message: Message content
            media_url: Optional remote/data URL for media attachment
                       Supports images, videos, audio, and documents based on file extension
            media_path: Optional local media file path (encoded to data URL)
            account: WhatsApp account to use
            message_id: Optional tracking ID for message correlation and status updates

        Returns:
            Result dict with ok status and messageId for tracking
        """
        normalized = normalize_phone(number)
        if not normalized:
            return {"ok": False, "error": "Number is required or invalid", "code": "VALIDATION_ERROR"}

        if not message and not media_url and not media_path:
            return {
                "ok": False,
                "error": "Message or media is required",
                "code": "VALIDATION_ERROR",
            }

        number = normalized
        final_media_url = media_url

        # Support local file attachments by converting to data URLs understood by the Node API.
        if media_path:
            media_result = self._media_path_to_data_url(media_path)
            if not media_result.get("ok"):
                return media_result
            final_media_url = media_result["data_url"]

        result = super().send(
            number=number,
            message=message or "",
            account=account,
            media_url=final_media_url,
            message_id=message_id,
        )

        with self.lock:
            self.stats["requests_total"] += 1
            if result.get("ok"):
                self.stats["requests_success"] += 1
            else:
                self.stats["requests_failed"] += 1

        return result

    def send_bulk(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Thin wrapper over the unified `/send-bulk` endpoint.
        """
        if not messages:
            return {"ok": False, "error": "No messages provided", "code": "VALIDATION_ERROR"}
        return super().send_bulk(messages=messages)

    # ------------------------------------------------------------------
    # Profile helpers (and aliases)
    # ------------------------------------------------------------------
    def check_profile(self, number: str, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Check a single WhatsApp profile, normalizing the phone input.
        
        Enhanced with WhiskeySockets/Baileys to return additional profile information:
        - profilePicUrl: URL to the user's profile picture (if available)
        - statusText: User's status message (if available)
        """
        normalized = normalize_phone(number)
        if not normalized:
            return {"ok": False, "error": "Number is required", "code": "VALIDATION_ERROR"}
        return super().profile_check(number=normalized, account=account)

    def check_profiles_bulk(
        self,
        numbers: List[str],
        account: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Bulk variant of `check_profile`.
        """
        if not numbers:
            return {"ok": False, "error": "No numbers provided", "code": "VALIDATION_ERROR"}
        cleaned = []
        for n in numbers:
            normalized = normalize_phone(n)
            if normalized:
                cleaned.append(normalized)
        if not cleaned:
            return {"ok": False, "error": "No valid numbers provided", "code": "VALIDATION_ERROR"}
        return super().profile_check_bulk(numbers=cleaned, account=account)

    # Backwards-compatible aliases expected by several UI tabs
    def profile_check(self, number: str, account: Optional[str] = None) -> Dict[str, Any]:
        return self.check_profile(number, account=account)

    def profile_check_bulk(self, numbers: List[str], account: Optional[str] = None) -> Dict[str, Any]:
        return self.check_profiles_bulk(numbers, account=account)

    # ------------------------------------------------------------------
    # Accounts / stats / misc
    # ------------------------------------------------------------------
    def logout(self, account: Optional[str] = None) -> Dict[str, Any]:
        return super().logout(account=account)

    def set_account(self, account_name: str) -> Dict[str, Any]:
        if not account_name:
            return {"ok": False, "error": "Account name required", "code": "VALIDATION_ERROR"}
        return super().set_account(account_name)

    def get_accounts(self) -> Dict[str, Any]:
        return super().get_accounts()

    def get_chat_list(self, account: Optional[str] = None) -> Dict[str, Any]:
        return super().get_chat_list(account=account)

    def get_all_contacts(self, account: Optional[str] = None) -> Dict[str, Any]:
        return super().get_all_contacts(account=account)

    def get_stats(self) -> Dict[str, Any]:
        return super().get_stats()

    def is_connected(self) -> bool:
        status = self.get_stats()
        if not status.get("ok"):
            return False
        if "connected" in status:
            return bool(status.get("connected"))
        connection = str(status.get("connection", "") or status.get("status", "")).strip().lower()
        return connection in {"open", "connected"}

    def get_api_stats(self) -> Dict[str, Any]:
        """
        Return lightweight client-side stats; transport metrics still live in
        the Node server and are available via `/stats`.
        """
        with self.lock:
            total = self.stats["requests_total"] or 1
            success_rate = (self.stats["requests_success"] / total) * 100 if total else 0
            return {
                **self.stats,
                "success_rate": success_rate,
                "host": self.base_url,
                "timeout": self.timeout,
            }

    def reset_stats(self) -> None:
        with self.lock:
            self.stats = {
                "requests_total": 0,
                "requests_success": 0,
                "requests_failed": 0,
                "last_request_time": None,
                "last_success_time": None,
                "connection_healthy": False,
            }
        logger.info("API statistics reset")

    # ------------------------------------------------------------------
    # Message Tracking Methods
    # ------------------------------------------------------------------
    def track_message(self, message_id: str, phone_number: str, content: str, 
                     account: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a message for tracking.
        
        Args:
            message_id: Unique tracking ID
            phone_number: Recipient phone number
            content: Message content
            account: WhatsApp account used
            
        Returns:
            Result dict with ok status
        """
        payload = {
            "messageId": message_id,
            "phoneNumber": phone_number,
            "content": content
        }
        if account:
            payload["account"] = account
        
        return self.post("/track-message", payload)
    
    def update_message_status(self, message_id: str, status: str) -> Dict[str, Any]:
        """
        Update message delivery status.
        
        Args:
            message_id: Message tracking ID
            status: New status (sent, delivered, read, played, failed)
            
        Returns:
            Result dict with ok status
        """
        payload = {"status": status}
        return self.post(f"/message-status/{message_id}", payload)
    
    def get_incoming_messages(self, since: Optional[int] = None) -> Dict[str, Any]:
        """
        Get incoming messages since specified timestamp.
        
        Args:
            since: Unix timestamp (optional, defaults to 24 hours ago)
            
        Returns:
            Result dict with messages list including:
            - sender: Phone number of sender
            - content: Message content
            - type: Message type (text, image, video, audio, document, sticker, location, contact, poll)
            - timestamp: When the message was received
            - jid: WhatsApp JID of the sender
            - messageId: Unique message ID
            - account: Account that received the message
            - pushName: Sender's display name (if available)
        """
        params = {}
        if since:
            params["since"] = since
        
        return self.get("/incoming-messages", params=params)
    
    def get_message_details(self, message_id: str) -> Dict[str, Any]:
        """
        Get details for a tracked message.
        
        Args:
            message_id: Message tracking ID
            
        Returns:
            Result dict with message details including delivery status
        """
        return self.get(f"/message/{message_id}")
    
    def get_all_tracked_messages(self) -> Dict[str, Any]:
        """
        Get all tracked messages.
        
        Returns:
            Result dict with all tracked messages
        """
        return self.get("/tracked-messages")
        
    # ------------------------------------------------------------------
    # Enhanced WhiskeySockets/Baileys Features
    # ------------------------------------------------------------------
    def connect_account(self, account: str, force_reset: bool = False, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Connect or reconnect a WhatsApp account.
        
        Args:
            account: Account name (e.g., "acc1")
            force_reset: Whether to reset the account state (logout)
            timeout: Optional custom timeout in seconds (default: 60s for session creation)
            
        Returns:
            Result dict with connection status
        """
        account = (account or "").strip()
        # Use longer timeout for session creation to match Node.js server's Baileys timeout (60s)
        effective_timeout = timeout if timeout is not None else 60.0
        if force_reset:
            # Directly hit reset endpoint with extended timeout
            return self._request("POST", f"/reset/{account}", timeout=effective_timeout)
        return super().connect_account(account, timeout=effective_timeout)
    
    def start_all_accounts(self) -> Dict[str, Any]:
        """
        Start all configured WhatsApp accounts (up to MAX_ACCOUNTS).
        
        Returns:
            Result dict with number of accounts started
        """
        return self.post("/start-all", {})

    def __repr__(self) -> str:
        return f"BaileysAPI(base_url={self.base_url!r}, timeout={self.timeout!r})"
