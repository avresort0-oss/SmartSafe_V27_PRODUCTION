"""
SmartSafe V27 - Live smoke test helper (CLI).

This script exercises the same backend calls used by these UI tabs:
- QR Login (`ui/tabs/qr_login_tab.py`)
- Single Engine (`ui/tabs/send_engine_tab.py`)
- Multi Engine (`ui/tabs/multi_engine_tab.py`)
- Bulk Sender PRO (`ui/tabs/bulk_sender_pro_tab.py`)

IMPORTANT:
- Only send messages to numbers you own or have explicit consent to message.
- Keep test volumes small to avoid account risk and policy violations.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.api.whatsapp_baileys import BaileysAPI
from core.engine.engine_service import EngineService
from core.engine.multi_engine import MultiEngine
from core.utils.contacts import load_contacts_from_csv, normalize_phone


DEFAULT_CONFIG_PATH = Path("logs/live_smoke_config.json")
DEFAULT_QR_PATH = Path("logs/qr_acc1.png")
DEFAULT_CSV_PATH = Path("logs/live_smoke_contacts.csv")


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _is_truthy(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _decode_data_url(data_url: str) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("Invalid data URL")
    _header, b64 = data_url.split(",", 1)
    return base64.b64decode(b64)


def _open_file_best_effort(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"[FAIL] Invalid JSON in {path}: {exc}")


def _save_template_config(path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise SystemExit(f"[FAIL] Config already exists: {path} (use --force to overwrite)")

    template = {
        "account": "acc1",
        "export_qr_path": str(DEFAULT_QR_PATH).replace("\\", "/"),
        "open_qr_after_export": True,
        "wait_connected_timeout_s": 180,
        "allow_send": False,
        "single_engine": {
            "to": "",
            "message": "SmartSafe V27 smoke test (Single Engine)",
        },
        "multi_engine": {
            "profile": "safe",
            "recipients": [
                {"phone": "", "name": "Test User"},
            ],
            "template": "Hello {name} (Multi Engine smoke test)",
            "timeout_s": 300,
        },
        "bulk_sender_pro": {
            "profile": "safe",
            "csv_path": str(DEFAULT_CSV_PATH).replace("\\", "/"),
            "recipients": [
                {"phone": "", "name": "Test User", "consent": True, "segment": "test"},
            ],
            "template": "Hello {name} (Bulk Sender smoke test)",
            "timeout_s": 300,
        },
    }

    _write_text(path, _json_dump(template) + "\n")


def _require_node_healthy(api: BaileysAPI) -> Dict[str, Any]:
    health = api.get_health()
    if not health.get("ok"):
        raise SystemExit(f"[FAIL] Node server not healthy: {health.get('error')}")
    return health


def export_qr(api: BaileysAPI, *, account: str, out_path: Path, open_after: bool, timeout_s: int = 30) -> Dict[str, Any]:
    deadline = time.time() + max(1, int(timeout_s))
    last: Dict[str, Any] = {}

    while time.time() < deadline:
        resp = api.get_qr(account)
        last = resp if isinstance(resp, dict) else {}

        if not last.get("ok"):
            time.sleep(1.0)
            continue

        if last.get("connected"):
            print("[OK] Account already connected; QR not required.")
            return last

        qr = last.get("qr")
        if isinstance(qr, str) and qr.startswith("data:"):
            try:
                png = _decode_data_url(qr)
            except Exception as exc:
                raise SystemExit(f"[FAIL] Failed to decode QR data URL: {exc}")
            _write_bytes(out_path, png)
            print(f"[OK] QR exported: {out_path}")
            if open_after:
                _open_file_best_effort(out_path)
            return last

        # QR not ready yet; keep polling.
        time.sleep(1.0)

    raise SystemExit(f"[FAIL] QR was not generated within {timeout_s}s. Last response:\n{_json_dump(last)}")


def wait_connected(api: BaileysAPI, *, account: str, timeout_s: int = 180, poll_s: float = 2.0) -> Dict[str, Any]:
    deadline = time.time() + max(1, int(timeout_s))
    last: Dict[str, Any] = {}

    while time.time() < deadline:
        resp = api.get_health(account=account)
        last = resp if isinstance(resp, dict) else {}

        if last.get("ok") and bool(last.get("connected")):
            print("[OK] Connected:", f"account={last.get('account') or account}", f"number={last.get('number') or '---'}")
            return last

        status = str(last.get("status") or "").strip()
        print("[WAIT] Not connected yet:", f"status={status or 'unknown'}")
        time.sleep(max(0.2, float(poll_s)))

    raise SystemExit(f"[FAIL] Not connected within {timeout_s}s. Last response:\n{_json_dump(last)}")


def _normalize_recipients(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        phone = normalize_phone(str(item.get("phone") or item.get("number") or "") or None)
        if not phone:
            continue
        out.append({**item, "phone": phone})
    return out


def send_single(api: BaileysAPI, *, to: str, message: str, account: Optional[str] = None) -> Dict[str, Any]:
    number = normalize_phone(to)
    if not number:
        raise SystemExit("[FAIL] Invalid phone number for single send (digits only, 10-15 length).")

    payload = api.send_message(number, message, account=account)
    print("[RESULT] Single Engine:", _json_dump(payload))
    return payload


def run_multi_engine(
    *,
    account: str,
    recipients: List[Dict[str, Any]],
    template: str,
    profile_name: str,
    timeout_s: int,
) -> Dict[str, Any]:
    contacts = [{"phone": r["phone"], "name": (r.get("name") or "User")} for r in recipients]
    engine = MultiEngine(profile_name=profile_name or "safe")

    print(f"[RUN] MultiEngine.send_bulk profile={engine.profile.name} contacts={len(contacts)}")
    result = engine.send_bulk(contacts=contacts, message_template=template, metadata={"source": "live_smoke_test"})
    if not result.get("ok"):
        raise SystemExit(f"[FAIL] MultiEngine job failed to start: {result.get('error') or result}")

    if not engine.completion_event.wait(timeout=max(1, int(timeout_s))):
        engine.stop()
        raise SystemExit("[FAIL] MultiEngine did not complete before timeout; job stopped.")

    stats = engine.get_stats()
    failed = engine.get_failed_contacts()
    print("[RESULT] MultiEngine stats:", _json_dump(stats))
    if failed:
        print("[WARN] MultiEngine failed contacts:", _json_dump(failed))
    return stats


def _write_contacts_csv(path: Path, recipients: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["phone", "name", "consent", "segment"])
        writer.writeheader()
        for r in recipients:
            writer.writerow(
                {
                    "phone": r.get("phone", ""),
                    "name": r.get("name", "User"),
                    "consent": r.get("consent", True),
                    "segment": r.get("segment", "test"),
                }
            )


def run_bulk_sender_pro(
    *,
    recipients: List[Dict[str, Any]],
    template: str,
    profile_name: str,
    csv_path: Path,
    timeout_s: int,
) -> Dict[str, Any]:
    _write_contacts_csv(csv_path, recipients)
    normalized = load_contacts_from_csv(csv_path, extra_fields=["custom1", "consent", "segment"])
    contacts = [
        {"phone": c.phone, "name": c.name, "account": c.account, **(c.extra or {})}
        for c in normalized
    ]

    service = EngineService()
    print(f"[RUN] EngineService.start_bulk_job profile={profile_name} contacts={len(contacts)} csv={csv_path}")
    result = service.start_bulk_job(
        contacts=contacts,
        message_template=template,
        profile_name=profile_name,
        metadata={"source": "live_smoke_test_bulk_sender_pro"},
    )
    if not result.get("ok"):
        raise SystemExit(f"[FAIL] Bulk Sender PRO job failed to start: {result.get('error') or result}")

    deadline = time.time() + max(1, int(timeout_s))
    while time.time() < deadline:
        stats = service.get_engine_stats() or {}
        if not stats.get("is_running"):
            print("[RESULT] Bulk Sender PRO stats:", _json_dump(stats))
            failed = service.get_failed_contacts()
            if failed:
                print("[WARN] Bulk Sender PRO failed contacts:", _json_dump(failed))
            return stats
        time.sleep(0.6)

    # Best-effort stop to avoid leaving it running.
    service.stop_job(service.get_active_job_id())
    raise SystemExit("[FAIL] Bulk Sender PRO did not complete before timeout; job stopped.")


@dataclass(frozen=True)
class SmokeConfig:
    account: str
    export_qr_path: Path
    open_qr_after_export: bool
    wait_connected_timeout_s: int
    allow_send: bool
    single_to: str
    single_message: str
    multi_profile: str
    multi_recipients: List[Dict[str, Any]]
    multi_template: str
    multi_timeout_s: int
    bulk_profile: str
    bulk_csv_path: Path
    bulk_recipients: List[Dict[str, Any]]
    bulk_template: str
    bulk_timeout_s: int


def _parse_config(raw: Dict[str, Any]) -> SmokeConfig:
    account = str(raw.get("account") or "acc1").strip().lower() or "acc1"
    export_qr_path = Path(str(raw.get("export_qr_path") or DEFAULT_QR_PATH))
    open_qr_after_export = bool(raw.get("open_qr_after_export", True))
    wait_connected_timeout_s = int(raw.get("wait_connected_timeout_s") or 180)
    allow_send = bool(raw.get("allow_send", False))

    single = raw.get("single_engine") or {}
    single_to = str(single.get("to") or "").strip()
    single_message = str(single.get("message") or "SmartSafe V27 smoke test (Single Engine)")

    multi = raw.get("multi_engine") or {}
    multi_profile = str(multi.get("profile") or "safe").strip().lower()
    multi_recipients = _normalize_recipients(list(multi.get("recipients") or []))
    multi_template = str(multi.get("template") or "Hello {name} (Multi Engine smoke test)")
    multi_timeout_s = int(multi.get("timeout_s") or 300)

    bulk = raw.get("bulk_sender_pro") or {}
    bulk_profile = str(bulk.get("profile") or "safe").strip().lower()
    bulk_csv_path = Path(str(bulk.get("csv_path") or DEFAULT_CSV_PATH))
    bulk_recipients = _normalize_recipients(list(bulk.get("recipients") or []))
    bulk_template = str(bulk.get("template") or "Hello {name} (Bulk Sender smoke test)")
    bulk_timeout_s = int(bulk.get("timeout_s") or 300)

    return SmokeConfig(
        account=account,
        export_qr_path=export_qr_path,
        open_qr_after_export=open_qr_after_export,
        wait_connected_timeout_s=wait_connected_timeout_s,
        allow_send=allow_send,
        single_to=single_to,
        single_message=single_message,
        multi_profile=multi_profile,
        multi_recipients=multi_recipients,
        multi_template=multi_template,
        multi_timeout_s=multi_timeout_s,
        bulk_profile=bulk_profile,
        bulk_csv_path=bulk_csv_path,
        bulk_recipients=bulk_recipients,
        bulk_template=bulk_template,
        bulk_timeout_s=bulk_timeout_s,
    )


def cmd_init(args: argparse.Namespace) -> None:
    path = Path(args.config)
    _save_template_config(path, force=bool(args.force))
    print(f"[OK] Wrote template config: {path}")
    print("Edit the JSON, then run: python tools/live_smoke_test.py all")


def cmd_health(_args: argparse.Namespace) -> None:
    api = BaileysAPI()
    health = _require_node_healthy(api)
    print("[OK] /health:", _json_dump(health))


def cmd_qr(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    api = BaileysAPI()
    _require_node_healthy(api)
    export_qr(
        api,
        account=cfg.account,
        out_path=cfg.export_qr_path,
        open_after=bool(cfg.open_qr_after_export),
        timeout_s=int(getattr(args, "timeout_s", 30) or 30),
    )


def cmd_wait(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    api = BaileysAPI()
    _require_node_healthy(api)
    wait_connected(api, account=cfg.account, timeout_s=int(getattr(args, "timeout_s", 0) or cfg.wait_connected_timeout_s))


def cmd_single(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    if not cfg.allow_send and not bool(args.allow_send):
        raise SystemExit("[FAIL] Sending is disabled. Set allow_send=true in config or pass --allow-send.")

    to = str(args.to or cfg.single_to).strip()
    msg = str(args.message or cfg.single_message)
    if not to:
        raise SystemExit("[FAIL] Missing recipient for single send (set single_engine.to in config or pass --to).")

    api = BaileysAPI()
    _require_node_healthy(api)
    send_single(api, to=to, message=msg, account=cfg.account)


def cmd_multi(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    if not cfg.allow_send and not bool(args.allow_send):
        raise SystemExit("[FAIL] Sending is disabled. Set allow_send=true in config or pass --allow-send.")

    recipients = cfg.multi_recipients
    if not recipients:
        raise SystemExit("[FAIL] No multi_engine.recipients configured.")

    run_multi_engine(
        account=cfg.account,
        recipients=recipients,
        template=cfg.multi_template,
        profile_name=str(cfg.multi_profile or "safe"),
        timeout_s=int(getattr(args, "timeout_s", 0) or cfg.multi_timeout_s),
    )


def cmd_bulk(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    if not cfg.allow_send and not bool(args.allow_send):
        raise SystemExit("[FAIL] Sending is disabled. Set allow_send=true in config or pass --allow-send.")

    recipients = cfg.bulk_recipients
    if not recipients:
        raise SystemExit("[FAIL] No bulk_sender_pro.recipients configured.")

    run_bulk_sender_pro(
        recipients=recipients,
        template=cfg.bulk_template,
        profile_name=str(cfg.bulk_profile or "safe"),
        csv_path=cfg.bulk_csv_path,
        timeout_s=int(getattr(args, "timeout_s", 0) or cfg.bulk_timeout_s),
    )


def cmd_all(args: argparse.Namespace) -> None:
    cfg = _parse_config(_load_config(Path(args.config)))
    api = BaileysAPI()

    _require_node_healthy(api)

    # 1) QR export (if not connected)
    export_qr(api, account=cfg.account, out_path=cfg.export_qr_path, open_after=cfg.open_qr_after_export, timeout_s=30)

    # 2) Wait for connection
    wait_connected(api, account=cfg.account, timeout_s=cfg.wait_connected_timeout_s)

    # 3) Optionally send
    if not cfg.allow_send and not bool(args.allow_send):
        print("[SKIP] Sending disabled (set allow_send=true in config or pass --allow-send).")
        return

    if cfg.single_to:
        send_single(api, to=cfg.single_to, message=cfg.single_message, account=cfg.account)
    else:
        print("[SKIP] single_engine.to is empty.")

    if cfg.multi_recipients:
        run_multi_engine(
            account=cfg.account,
            recipients=cfg.multi_recipients,
            template=cfg.multi_template,
            profile_name=cfg.multi_profile,
            timeout_s=cfg.multi_timeout_s,
        )
    else:
        print("[SKIP] multi_engine.recipients is empty.")

    if cfg.bulk_recipients:
        run_bulk_sender_pro(
            recipients=cfg.bulk_recipients,
            template=cfg.bulk_template,
            profile_name=cfg.bulk_profile,
            csv_path=cfg.bulk_csv_path,
            timeout_s=cfg.bulk_timeout_s,
        )
    else:
        print("[SKIP] bulk_sender_pro.recipients is empty.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SmartSafe V27 live smoke-test helper.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to JSON config (default: logs/live_smoke_config.json)")

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Write a template config under logs/ (gitignored).")
    s.add_argument("--force", action="store_true", help="Overwrite existing config.")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("health", help="Check Node server /health.")
    s.set_defaults(func=cmd_health)

    s = sub.add_parser("qr", help="Export QR image for the configured account.")
    s.add_argument("--timeout-s", type=int, default=30)
    s.set_defaults(func=cmd_qr)

    s = sub.add_parser("wait", help="Wait until the configured account is connected.")
    s.add_argument("--timeout-s", type=int, default=0, help="Override wait timeout (seconds).")
    s.set_defaults(func=cmd_wait)

    s = sub.add_parser("single", help="Send a single message (Single Engine).")
    s.add_argument("--to", default="", help="Recipient phone (digits only).")
    s.add_argument("--message", default="", help="Message text.")
    s.add_argument("--allow-send", action="store_true", help="Enable sending even if config has allow_send=false.")
    s.set_defaults(func=cmd_single)

    s = sub.add_parser("multi", help="Run a MultiEngine bulk job.")
    s.add_argument("--timeout-s", type=int, default=0, help="Override job timeout (seconds).")
    s.add_argument("--allow-send", action="store_true", help="Enable sending even if config has allow_send=false.")
    s.set_defaults(func=cmd_multi)

    s = sub.add_parser("bulk", help="Run a Bulk Sender PRO-style job (CSV load + EngineService).")
    s.add_argument("--timeout-s", type=int, default=0, help="Override job timeout (seconds).")
    s.add_argument("--allow-send", action="store_true", help="Enable sending even if config has allow_send=false.")
    s.set_defaults(func=cmd_bulk)

    s = sub.add_parser("all", help="Run QR export -> wait connected -> optional sends.")
    s.add_argument("--allow-send", action="store_true", help="Enable sending even if config has allow_send=false.")
    s.set_defaults(func=cmd_all)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
