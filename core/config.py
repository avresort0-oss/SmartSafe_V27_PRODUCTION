"""
Central runtime configuration for SmartSafe.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    # Optional .env loader for local development.
    # If the package is missing, environment variables are read from the OS only.
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - extremely small surface
    load_dotenv = None  # type: ignore[assignment]

if load_dotenv is not None:
    # Load a root-level .env file if present. This keeps configuration
    # centralized without forcing .env usage in production.
    project_root = Path(__file__).resolve().parents[1]
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip()


@dataclass(frozen=True)
class Settings:
    # Core API client settings
    api_host: str
    api_timeout: int
    api_max_retries: int
    api_retry_delay: float
    ui_request_timeout: float
    api_key: str

    # Feature flags
    enable_experimental_tabs: bool

    # Recipient history persistence (ban-safe caps)
    enable_recipient_store: bool
    recipient_store_path: str

    # Compliance / Phase C
    enable_dnc_registry: bool
    dnc_registry_path: str
    enable_profile_precheck: bool
    profile_precheck_batch_size: int

    enable_segment_caps: bool
    segment_hourly_limit: int
    segment_daily_limit: int

    # Spam detection settings
    spam_detection_enabled: bool
    spam_detection_threshold: int
    spam_detection_patterns: List[str]
    spam_detection_auto_block: bool

    # Node server defaults
    node_host: str
    node_port: int
    require_api_key: bool

    # Webhook API settings
    webhook_api_enabled: bool
    webhook_api_host: str
    webhook_api_port: int
    webhook_api_key: str

    # Smart Anti-Ban Engine settings
    enable_proxy_rotation: bool
    proxy_rotation_interval: int
    proxies_file: str
    read_receipt_mode: str  # 'auto', 'off', 'manual'
    enable_session_backup: bool
    google_drive_creds_path: str
    session_backup_interval: int


def load_settings() -> Settings:
    node_host = _env_str("SMARTSAFE_NODE_HOST", "127.0.0.1")
    node_port = _env_int("SMARTSAFE_NODE_PORT", 4000)
    default_api_host = f"http://{node_host}:{node_port}"
    project_root = Path(__file__).resolve().parents[1]
    default_recipient_store_path = str((project_root / "logs" / "recipient_history.sqlite3").resolve())
    default_dnc_registry_path = str((project_root / "logs" / "dnc_registry.sqlite3").resolve())

    return Settings(
        api_host=_env_str("SMARTSAFE_API_HOST", default_api_host).rstrip("/"),
        api_timeout=_env_int("SMARTSAFE_API_TIMEOUT", 30),
        api_max_retries=_env_int("SMARTSAFE_API_MAX_RETRIES", 3),
        api_retry_delay=_env_float("SMARTSAFE_API_RETRY_DELAY", 2.0),
        ui_request_timeout=_env_float("SMARTSAFE_UI_REQUEST_TIMEOUT", 10.0),
        api_key=_env_str("SMARTSAFE_API_KEY", ""),
        enable_experimental_tabs=_env_bool("SMARTSAFE_ENABLE_EXPERIMENTAL_TABS", False),
        enable_recipient_store=_env_bool("SMARTSAFE_ENABLE_RECIPIENT_STORE", True),
        recipient_store_path=_env_str("SMARTSAFE_RECIPIENT_STORE_PATH", default_recipient_store_path),

        enable_dnc_registry=_env_bool("SMARTSAFE_ENABLE_DNC_REGISTRY", True),
        dnc_registry_path=_env_str("SMARTSAFE_DNC_REGISTRY_PATH", default_dnc_registry_path),
        enable_profile_precheck=_env_bool("SMARTSAFE_ENABLE_PROFILE_PRECHECK", False),
        profile_precheck_batch_size=_env_int("SMARTSAFE_PROFILE_PRECHECK_BATCH_SIZE", 200),

        enable_segment_caps=_env_bool("SMARTSAFE_ENABLE_SEGMENT_CAPS", False),
        segment_hourly_limit=_env_int("SMARTSAFE_SEGMENT_HOURLY_LIMIT", 0),
        segment_daily_limit=_env_int("SMARTSAFE_SEGMENT_DAILY_LIMIT", 0),

        spam_detection_enabled=_env_bool("SMARTSAFE_SPAM_DETECTION_ENABLED", True),
        spam_detection_threshold=_env_int("SMARTSAFE_SPAM_DETECTION_THRESHOLD", 2),
        spam_detection_patterns=_env_str("SMARTSAFE_SPAM_DETECTION_PATTERNS", "").split(","),
        spam_detection_auto_block=_env_bool("SMARTSAFE_SPAM_DETECTION_AUTO_BLOCK", False),

        node_host=node_host,
        node_port=node_port,
        require_api_key=_env_bool("SMARTSAFE_REQUIRE_API_KEY", False),

        webhook_api_enabled=_env_bool("SMARTSAFE_WEBHOOK_API_ENABLED", False),
        webhook_api_host=_env_str("SMARTSAFE_WEBHOOK_API_HOST", "127.0.0.1"),
        webhook_api_port=_env_int("SMARTSAFE_WEBHOOK_API_PORT", 8000),
        webhook_api_key=_env_str("SMARTSAFE_WEBHOOK_API_KEY", ""),

        # Smart Anti-Ban Engine
        enable_proxy_rotation=_env_bool("SMARTSAFE_ENABLE_PROXY_ROTATION", True),
        proxy_rotation_interval=_env_int("SMARTSAFE_PROXY_ROTATION_INTERVAL", 10),
        proxies_file=_env_str("SMARTSAFE_PROXIES_FILE", "proxies.json"),
        read_receipt_mode=_env_str("SMARTSAFE_READ_RECEIPT_MODE", "auto"),
        enable_session_backup=_env_bool("SMARTSAFE_ENABLE_SESSION_BACKUP", True),
        google_drive_creds_path=_env_str("SMARTSAFE_GOOGLE_DRIVE_CREDS", "google_drive_creds.json"),
        session_backup_interval=_env_int("SMARTSAFE_SESSION_BACKUP_INTERVAL", 3600),
    )


SETTINGS = load_settings()
