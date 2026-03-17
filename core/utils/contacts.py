from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class NormalizedContact:
    """
    Lightweight representation of a contact loaded from CSV or text.

    The `phone` field is always a digits-only, validation-checked string that is
    suitable for passing directly to the Node/Baileys layer.
    """

    phone: str
    name: str = "User"
    account: Optional[str] = None
    extra: Dict[str, Any] | None = None


def _parse_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        try:
            return bool(int(value))
        except Exception:
            return None
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on", "allow", "allowed"}:
        return True
    if s in {"0", "false", "no", "n", "off", "deny", "denied"}:
        return False
    return None


def normalize_phone(
    raw: str | None,
    *,
    default_country_code: str | None = None,
    min_length: int = 10,
    max_length: int = 15,
) -> Optional[str]:
    """
    Normalize a phone string into a digits-only representation.

    - Strips all non-digit characters (spaces, dashes, +, brackets, etc.).
    - Optionally applies a `default_country_code` for local-style inputs.
    - Enforces a length window; returns ``None`` for invalid numbers.

    This helper is intentionally conservative and is meant to be shared by both
    UI tabs and the Baileys API layer.
    """
    if not raw:
        return None

    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None

    # Country-specific tweaks. For now we mirror the existing Bangladesh logic
    # used in `ProfileCheckerTab.clean_numbers`.
    if default_country_code:
        if default_country_code == "880":
            if len(digits) == 11 and digits.startswith("0"):
                digits = default_country_code + digits[1:]
            elif len(digits) == 10:
                digits = default_country_code + digits

    if len(digits) < min_length or len(digits) > max_length:
        return None

    return digits


def normalize_numbers(
    numbers: Iterable[str],
    *,
    default_country_code: str | None = None,
    min_length: int = 10,
    max_length: int = 15,
    deduplicate: bool = True,
) -> List[str]:
    """
    Normalize and optionally deduplicate a collection of phone numbers.
    """
    seen: set[str] = set()
    result: List[str] = []

    for raw in numbers:
        normalized = normalize_phone(
            raw,
            default_country_code=default_country_code,
            min_length=min_length,
            max_length=max_length,
        )
        if not normalized:
            continue
        if deduplicate and normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


def load_contacts_from_csv(
    path: str | Path,
    *,
    default_country_code: str | None = None,
    encoding: str = "utf-8-sig",
    phone_fields: Iterable[str] = ("phone", "number", "phone_number"),
    name_field: str = "name",
    account_field: str = "account",
    extra_fields: Optional[Iterable[str]] = None,
    consent_field: str = "consent",
    segment_field: str = "segment",
) -> List[NormalizedContact]:
    """
    Load and normalize contacts from a CSV file.

    The loader is intentionally small and opinionated:
    - Uses the first non-empty field from `phone_fields` as the phone source.
    - Applies `normalize_phone` and skips rows with invalid numbers.
    - Pulls a display name from ``name_field`` (defaulting to ``"User"``).
    - Optionally extracts a lowercased account identifier.
    - Returns ``NormalizedContact`` instances that can be further adapted by UI
      tabs (e.g. to simple dicts) without re-implementing the CSV logic.
    """
    path = Path(path)
    contacts: List[NormalizedContact] = []

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding=encoding, newline="") as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            if not row:
                continue

            raw_phone: Optional[str] = None
            for field in phone_fields:
                value = row.get(field)
                if value:
                    raw_phone = str(value)
                    break

            phone = normalize_phone(raw_phone, default_country_code=default_country_code)
            if not phone:
                continue

            name = (row.get(name_field) or "User").strip() or "User"
            account_raw = (row.get(account_field) or "").strip().lower() or None

            extras: Dict[str, Any] | None = None
            extra_keys = list(extra_fields) if extra_fields else []

            # Phase C: always attempt to carry consent/segment forward if present.
            if consent_field and consent_field not in extra_keys and consent_field in row:
                extra_keys.append(consent_field)
            if segment_field and segment_field not in extra_keys and segment_field in row:
                extra_keys.append(segment_field)

            if extra_keys:
                extras = {key: row.get(key) for key in extra_keys}
                # Normalize consent/segment into consistent shapes when present.
                if consent_field and consent_field in extras:
                    parsed = _parse_bool(extras.get(consent_field))
                    if parsed is not None:
                        extras[consent_field] = parsed
                if segment_field and segment_field in extras:
                    seg = (extras.get(segment_field) or "").strip()
                    extras[segment_field] = seg.lower() if seg else ""

            contacts.append(
                NormalizedContact(
                    phone=phone,
                    name=name,
                    account=account_raw,
                    extra=extras,
                )
            )

    return contacts

