from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.utils.contacts import normalize_phone


_RE_WS = re.compile(r"\s+")


def _truthy(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on", "allow", "allowed", "consent", "ok"}:
        return True
    if s in {"0", "false", "no", "n", "off", "deny", "denied", "block", "blocked"}:
        return False
    return None


def normalize_segment(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = _RE_WS.sub(" ", s)
    return s.lower()


@dataclass(frozen=True)
class OptOutMatch:
    ok: bool
    keyword: Optional[str]


_OPTOUT_KEYWORDS = [
    # English
    "stop",
    "unsubscribe",

    "opt out",
    "optout",
    "remove me",
    "do not contact",
    "dont contact",
    "dnc",
    "dnd",
    "cancel",
    "end",
    # Bangla (common)
    "বন্ধ",
    "স্টপ",
    "আনসাবস্ক্রাইব",
    "মুছে ফেল",
    "বন্ধ করুন",
    # Hindi/Urdu (common)
    "बंद",
    "स्टॉप",
    "हटा दो",

    "unsubscribe",
    #Spanish
    "Parar",
    "Anular la suscripción",
    "Darse de baja",
    #French
    "Arrêter",
    "Se désabonner",
    #German
    "Stoppen",
    "Abmelden",
    #Italian
    "Fermare",
    "Annulla l'iscrizione",
    #Portuguese
    "Parar",
    "Cancelar subscrição",

]







def detect_opt_out(text: str | None) -> OptOutMatch:
    """
    Best-effort opt-out detection from inbound text.
    """
    s = (text or "").strip().lower()
    if not s:
        return OptOutMatch(ok=False, keyword=None)

    s = _RE_WS.sub(" ", s)
    for kw in _OPTOUT_KEYWORDS:
        k = kw.lower()
        if not k:
            continue
        # Word-boundary match for ascii tokens, substring for others.
        if all("a" <= ch <= "z" or ch == " " for ch in k):
            pattern = r"(?:^|\b)" + re.escape(k) + r"(?:\b|$)"
            if re.search(pattern, s):
                return OptOutMatch(ok=True, keyword=kw)
        else:
            if k in s:
                return OptOutMatch(ok=True, keyword=kw)
    return OptOutMatch(ok=False, keyword=None)


@dataclass(frozen=True)
class ContactDrop:
    contact: Dict[str, Any]
    reason: str


def _contact_phone_source(contact: Dict[str, Any]) -> Any:
    return contact.get("phone") or contact.get("number") or contact.get("phone_number")


def normalize_and_dedupe_contacts(
    contacts: Iterable[Dict[str, Any]],
    *,
    default_country_code: str | None = None,
    min_length: int = 10,
    max_length: int = 15,
) -> Tuple[List[Dict[str, Any]], List[ContactDrop], Dict[str, int]]:
    """
    Normalize phone numbers and remove duplicates.
    """
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    drops: List[ContactDrop] = []
    summary = {"invalid": 0, "duplicates": 0}

    for c in contacts or []:
        if not isinstance(c, dict):
            continue
        raw = _contact_phone_source(c)
        number = normalize_phone(
            str(raw) if raw is not None else None,
            default_country_code=default_country_code,
            min_length=min_length,
            max_length=max_length,
        )
        if not number:
            summary["invalid"] += 1
            drops.append(ContactDrop(contact=c, reason="invalid_phone"))
            continue
        if number in seen:
            summary["duplicates"] += 1
            drops.append(ContactDrop(contact={**c, "phone": number}, reason="duplicate_phone"))
            continue
        seen.add(number)
        # Preserve original contact fields but force canonical `phone`.
        out.append({**c, "phone": number})

    return out, drops, summary


def filter_by_consent_and_segment(
    contacts: Iterable[Dict[str, Any]],
    *,
    default_consent: bool = True,
    consent_field: str = "consent",
    segment_field: str = "segment",
) -> Tuple[List[Dict[str, Any]], List[ContactDrop], Dict[str, int]]:
    """
    Drop contacts with consent explicitly false and normalize segment labels.
    """
    out: List[Dict[str, Any]] = []
    drops: List[ContactDrop] = []
    summary = {"no_consent": 0}

    for c in contacts or []:
        if not isinstance(c, dict):
            continue
        consent_raw = c.get(consent_field)
        consent = _truthy(consent_raw)
        if consent is None:
            consent = bool(default_consent)
        if not consent:
            summary["no_consent"] += 1
            drops.append(ContactDrop(contact=c, reason="no_consent"))
            continue

        seg = normalize_segment(c.get(segment_field))
        if seg is not None:
            out.append({**c, segment_field: seg})
        else:
            out.append({**c})

    return out, drops, summary


def filter_by_dnc(
    contacts: Iterable[Dict[str, Any]],
    *,
    dnc_registry: Any,
) -> Tuple[List[Dict[str, Any]], List[ContactDrop], Dict[str, int]]:
    """
    Drop contacts present in a DNC registry.
    """
    out: List[Dict[str, Any]] = []
    drops: List[ContactDrop] = []
    summary = {"dnc_blocked": 0}

    for c in contacts or []:
        if not isinstance(c, dict):
            continue
        n = c.get("phone") or _contact_phone_source(c)
        blocked = False
        try:
            blocked = bool(dnc_registry.is_blocked(n))  # type: ignore[attr-defined]
        except Exception:
            blocked = False
        if blocked:
            summary["dnc_blocked"] += 1
            drops.append(ContactDrop(contact=c, reason="dnc_blocked"))
            continue
        out.append(c)

    return out, drops, summary


def profile_check_filter(
    api: Any,
    contacts: Iterable[Dict[str, Any]],
    *,
    batch_size: int = 200,
    default_account: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], List[ContactDrop], Dict[str, int], Dict[str, Any]]:
    """
    Optional pre-check pipeline stage: bulk profile existence check.

    Fail-open policy:
    - If the API is unreachable or returns an unexpected shape, this function
      returns the original list and a warning in `meta`.
    """
    out: List[Dict[str, Any]] = []
    drops: List[ContactDrop] = []
    summary = {"profile_inactive": 0, "profile_unknown": 0}
    meta: Dict[str, Any] = {"ok": True}

    items = [c for c in (contacts or []) if isinstance(c, dict)]
    if not items:
        return [], [], summary, meta

    bs = max(1, min(int(batch_size), 500))
    # Group by account to respect multi-account routing.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in items:
        acc = (c.get("account") or default_account or "").strip().lower()
        groups.setdefault(acc, []).append(c)

    ts = float(now_ts if now_ts is not None else time.time())
    meta["checked_at_ts"] = ts
    meta["groups"] = {k or "default": len(v) for k, v in groups.items()}

    for acc, group in groups.items():
        # chunk and bulk-check
        for i in range(0, len(group), bs):
            chunk = group[i : i + bs]
            numbers = [str(c.get("phone") or _contact_phone_source(c) or "") for c in chunk]
            try:
                resp = api.profile_check_bulk(numbers, account=(acc or None))  # type: ignore[attr-defined]
            except Exception as exc:
                meta.update({"ok": False, "warning": f"profile_check_bulk failed: {exc}"})
                # fail-open
                return items, [], summary, meta

            if not isinstance(resp, dict) or "results" not in resp:
                meta.update({"ok": False, "warning": "profile_check_bulk returned unexpected payload"})
                return items, [], summary, meta

            results = resp.get("results") or []
            if not isinstance(results, list) or len(results) != len(chunk):
                meta.update({"ok": False, "warning": "profile_check_bulk results length mismatch"})
                return items, [], summary, meta

            for c, r in zip(chunk, results):
                if not isinstance(r, dict):
                    summary["profile_unknown"] += 1
                    out.append(c)
                    continue

                exists = r.get("exists")
                if exists is True:
                    out.append(c)
                elif exists is False:
                    summary["profile_inactive"] += 1
                    drops.append(ContactDrop(contact=c, reason="profile_inactive"))
                else:
                    # Unknown shape or backend failure; keep contact (fail-open),
                    # but record a counter.
                    summary["profile_unknown"] += 1
                    out.append(c)

    return out, drops, summary, meta

