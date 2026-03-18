"""
Shared Node API service with normalized responses and timeouts.

This module defines the single **Python ↔ Node** transport boundary used by the
rest of the application. All HTTP calls to the WhatsApp Node server must go
through `NodeService` (or a subclass such as `BaileysAPI`) so that:

- Responses are normalized to a stable shape (`ok`, `error`, `code`,
  `status_code`, `retryable`).
- Timeouts, connection errors, and JSON/shape issues are handled consistently.

The JSON contracts for the underlying endpoints (`/health`, `/status`,
`/accounts[-status]`, `/stats`, `/send`, `/send-bulk`,
`/profile-check[-bulk]`) are documented in `NODE_CONTRACTS.md`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
import pybreaker
import time

from core.config import SETTINGS
from core.monitoring.metrics import record_api_request

NodeResponse = Dict[str, Any]


logger = logging.getLogger(__name__)


class NodeService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or SETTINGS.api_host).rstrip("/")
        self.timeout = timeout if timeout is not None else SETTINGS.ui_request_timeout
        self.session = requests.Session()

        key = api_key if api_key is not None else SETTINGS.api_key
        if key:
            self.session.headers.update({"X-API-Key": key})

        # Circuit breaker for API resilience
        self.circuit_breaker = pybreaker.CircuitBreaker(
            fail_max=5,  # Max failures before opening
            reset_timeout=60,  # Seconds to wait before retrying
        )

    def _do_request(self, method, path, json_data=None, params=None, timeout=None):
        """Actual request implementation."""
        url = f"{self.base_url}{path}"
        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = time.time()
        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                json=json_data,
                params=params,
                timeout=effective_timeout,
            )
        except requests.exceptions.Timeout:
            return self._normalize_error(
                "Request timed out",
                code="TIMEOUT",
                status_code=0,
                retryable=True,
            )
        except requests.exceptions.ConnectionError:
            return self._normalize_error(
                "Cannot connect to Node server",
                code="CONNECTION_ERROR",
                status_code=0,
                retryable=True,
            )
        except requests.exceptions.RequestException as exc:
            logger.error("NodeService request error: %s", exc, exc_info=True)
            return self._normalize_error(
                str(exc),
                code="REQUEST_EXCEPTION",
                status_code=0,
                retryable=False,
            )

        try:
            data = resp.json()
        except ValueError:
            return self._normalize_error(
                "Invalid JSON response from server",
                code="INVALID_JSON",
                details={"status_code": resp.status_code},
                status_code=resp.status_code,
                retryable=False,
            )

        if not isinstance(data, dict):
            return self._normalize_error(
                "Unexpected response payload",
                code="INVALID_PAYLOAD",
                details={"status_code": resp.status_code},
                status_code=resp.status_code,
                retryable=False,
            )

        status_code = resp.status_code

        # Always normalize the response shape
        normalized = {
            "ok": data.get("ok", False) if status_code < 400 else False,
            "error": data.get("error", f"HTTP {status_code}"),
            "code": data.get("code", "UNKNOWN_ERROR"),
            "status_code": status_code,
            "retryable": data.get(
                "retryable", status_code in {408, 429, 500, 502, 503, 504}
            ),
        }

        # Preserve other fields from the original response
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value

        # Record metrics
        duration = time.time() - start_time
        record_api_request(method.upper(), path, status_code, duration)

        return normalized

    def _request(self, method, path, *, json_data=None, params=None, timeout=None):
        """Request with circuit breaker."""
        return self.circuit_breaker.call(
            self._do_request, method, path, json_data, params, timeout
        )

    def _normalize_error(
        self,
        message: str,
        code: str = "REQUEST_FAILED",
        details: Optional[Any] = None,
        status_code: int = 0,
        retryable: bool = False,
    ) -> NodeResponse:
        """
        Return a normalized error payload shared across all Node API callers.

        The shape is intentionally stable so higher‑level components (engine,
        UI, tests) can rely on common fields:

        - ok: bool
        - error: human‑readable message
        - code: machine‑readable error code
        - status_code: HTTP status code when available (0 for local failures)
        - retryable: whether the error is considered transient
        - details: optional extra context
        """
        payload: Dict[str, Any] = {
            "ok": False,
            "error": message,
            "code": code,
            "status_code": status_code,
            "retryable": retryable,
        }
        if details is not None:
            payload["details"] = details
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> NodeResponse:
        url = f"{self.base_url}{path}"
        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = time.time()
        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                json=json_data,
                params=params,
                timeout=effective_timeout,
            )
        except requests.exceptions.Timeout:
            return self._normalize_error(
                "Request timed out",
                code="TIMEOUT",
                status_code=0,
                retryable=True,
            )
        except requests.exceptions.ConnectionError:
            return self._normalize_error(
                "Cannot connect to Node server",
                code="CONNECTION_ERROR",
                status_code=0,
                retryable=True,
            )
        except requests.exceptions.RequestException as exc:
            logger.error("NodeService request error: %s", exc, exc_info=True)
            return self._normalize_error(
                str(exc),
                code="REQUEST_EXCEPTION",
                status_code=0,
                retryable=False,
            )

        try:
            data = resp.json()
        except ValueError:
            return self._normalize_error(
                "Invalid JSON response from server",
                code="INVALID_JSON",
                details={"status_code": resp.status_code},
                status_code=resp.status_code,
                retryable=False,
            )

        if not isinstance(data, dict):
            return self._normalize_error(
                "Unexpected response payload",
                code="INVALID_PAYLOAD",
                details={"status_code": resp.status_code},
                status_code=resp.status_code,
                retryable=False,
            )

        status_code = resp.status_code

        # Always normalize the response shape
        normalized = {
            "ok": data.get("ok", False) if status_code < 400 else False,
            "error": data.get("error", f"HTTP {status_code}"),
            "code": data.get("code", "UNKNOWN_ERROR"),
            "status_code": status_code,
            "retryable": data.get(
                "retryable", status_code in {408, 429, 500, 502, 503, 504}
            ),
        }

        # Preserve other fields from the original response
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value

        # Record metrics
        duration = time.time() - start_time
        record_api_request(method.upper(), path, status_code, duration)

        return normalized

    def get_health(self) -> NodeResponse:
        return self._request("GET", "/health")

    # Backwards-compatible generic HTTP helpers
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> NodeResponse:
        """Generic GET helper accepting an API path (e.g. '/incoming-messages')."""
        return self._request("GET", path, params=params)

    def post(
        self, path: str, json_data: Optional[Dict[str, Any]] = None
    ) -> NodeResponse:
        """Generic POST helper accepting an API path and optional JSON body."""
        return self._request("POST", path, json_data=json_data)

    def put(
        self, path: str, json_data: Optional[Dict[str, Any]] = None
    ) -> NodeResponse:
        return self._request("PUT", path, json_data=json_data)

    def delete(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> NodeResponse:
        return self._request("DELETE", path, params=params)

    def get_status(self, account: Optional[str] = None) -> NodeResponse:
        params = {"account": account} if account else None
        return self._request("GET", "/status", params=params)

    def get_qr(self, account: Optional[str] = None) -> NodeResponse:
        if account:
            return self._request("GET", f"/qr/{account}")
        return self._request("GET", "/qr")

    def get_pairing_code(self, account: str, number: str) -> NodeResponse:
        """
        Request a pairing code for the given account and phone number.
        Required for 'Link with phone number' functionality.
        """
        payload = {"account": account, "number": number}
        return self._request("POST", "/pairing-code", json_data=payload)

    def get_accounts(self) -> NodeResponse:
        return self._request("GET", "/accounts")

    def get_accounts_status(self) -> NodeResponse:
        return self._request("GET", "/accounts-status")

    def get_stats(self) -> NodeResponse:
        return self._request("GET", "/stats")

    def get_chat_list(self, account: Optional[str] = None) -> NodeResponse:
        params = {"account": account} if account else None
        return self._request("GET", "/chat-list", params=params)

    def get_all_contacts(self, account: Optional[str] = None) -> NodeResponse:
        params = {"account": account} if account else None
        return self._request("GET", "/all-contacts", params=params)

    def set_account(self, account: str) -> NodeResponse:
        return self._request("POST", "/set-account", json_data={"account": account})

    def reset_account(self, account: str) -> NodeResponse:
        return self._request("POST", f"/reset/{account}")

    def connect_account(
        self, account: str, timeout: Optional[float] = None
    ) -> NodeResponse:
        """
        Connect or reconnect a WhatsApp account.

        Args:
            account: Account name
            timeout: Optional custom timeout in seconds (default: 60s for session creation)

        Returns:
            NodeResponse with connection status
        """
        # Use 60s default timeout for session creation to match Node.js server's Baileys timeout
        effective_timeout = timeout if timeout is not None else 60.0
        return self._request("POST", f"/connect/{account}", timeout=effective_timeout)

    def logout(self, account: Optional[str] = None) -> NodeResponse:
        params = {"account": account} if account else None
        return self._request("GET", "/logout", params=params)

    def send(
        self,
        number: str,
        message: str,
        *,
        account: Optional[str] = None,
        media_url: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> NodeResponse:
        payload: Dict[str, Any] = {"number": number, "message": message}
        if account:
            payload["account"] = account
        if media_url:
            payload["media_url"] = media_url
        if message_id:
            payload["messageId"] = message_id
        return self._request("POST", "/send", json_data=payload)

    def send_bulk(
        self,
        messages: List[Dict[str, Any]],
        *,
        account: Optional[str] = None,
    ) -> NodeResponse:
        payload: Dict[str, Any] = {"messages": messages}
        if account:
            payload["account"] = account
        return self._request("POST", "/send-bulk", json_data=payload)

    def profile_check(
        self, number: str, *, account: Optional[str] = None
    ) -> NodeResponse:
        payload: Dict[str, Any] = {"number": number}
        if account:
            payload["account"] = account
        return self._request("POST", "/profile-check", json_data=payload)

    def profile_check_bulk(
        self,
        numbers: List[str],
        *,
        account: Optional[str] = None,
    ) -> NodeResponse:
        payload: Dict[str, Any] = {"numbers": numbers}
        if account:
            payload["account"] = account
        return self._request("POST", "/profile-check-bulk", json_data=payload)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass
