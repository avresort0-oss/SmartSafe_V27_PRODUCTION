from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "logs" / "profile_contact_lists.json"
_STORE_LOCK = threading.Lock()
_STORE_INSTANCE: Optional["ProfileContactListStore"] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ProfileContactListStore:
    """JSON-backed saved collection store for reusable profile/contact datasets."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path is not None else _DEFAULT_PATH
        self._lock = threading.Lock()
        self._collections: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                self._collections = {}
                return
            with self.path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            self._collections = {}
            return

        collections = payload.get("collections", []) if isinstance(payload, dict) else []
        if not isinstance(collections, list):
            self._collections = {}
            return

        loaded: Dict[str, Dict[str, Any]] = {}
        for item in collections:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip()
            if not cid:
                continue
            loaded[cid] = deepcopy(item)
        self._collections = loaded

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "collections": sorted(
                [deepcopy(item) for item in self._collections.values()],
                key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
                reverse=True,
            )
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp.replace(self.path)

    def list_collections(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = []
            for item in self._collections.values():
                rows.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "source": item.get("source"),
                        "account": item.get("account"),
                        "row_count": int(item.get("row_count") or 0),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    }
                )
            rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
            return rows

    def get_collection(self, collection_id: str) -> Optional[Dict[str, Any]]:
        cid = str(collection_id or "").strip()
        if not cid:
            return None
        with self._lock:
            item = self._collections.get(cid)
            return deepcopy(item) if item is not None else None

    def save_collection(
        self,
        name: str,
        rows: List[Dict[str, Any]],
        *,
        source: str,
        account: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cleaned_name = str(name or "").strip()
        if not cleaned_name:
            cleaned_name = f"list-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        now_iso = _utc_now_iso()
        safe_rows = [deepcopy(row) for row in (rows or []) if isinstance(row, dict)]
        metadata_copy = deepcopy(metadata) if isinstance(metadata, dict) else {}

        with self._lock:
            existing = next(
                (
                    item
                    for item in self._collections.values()
                    if str(item.get("name") or "").strip().casefold() == cleaned_name.casefold()
                ),
                None,
            )

            if existing is None:
                cid = uuid.uuid4().hex
                record = {
                    "id": cid,
                    "name": cleaned_name,
                    "created_at": now_iso,
                }
            else:
                cid = str(existing.get("id"))
                record = deepcopy(existing)

            record.update(
                {
                    "id": cid,
                    "name": cleaned_name,
                    "source": str(source or "").strip() or "unknown",
                    "account": str(account or "").strip() or None,
                    "row_count": len(safe_rows),
                    "updated_at": now_iso,
                    "rows": safe_rows,
                    "metadata": metadata_copy,
                }
            )
            self._collections[cid] = record
            self._flush()
            return deepcopy(record)

    def delete_collection(self, collection_id: str) -> bool:
        cid = str(collection_id or "").strip()
        if not cid:
            return False
        with self._lock:
            if cid not in self._collections:
                return False
            del self._collections[cid]
            self._flush()
            return True


def get_profile_contact_list_store(path: Optional[str | Path] = None) -> ProfileContactListStore:
    global _STORE_INSTANCE
    if path is not None:
        return ProfileContactListStore(path=path)

    with _STORE_LOCK:
        if _STORE_INSTANCE is None:
            _STORE_INSTANCE = ProfileContactListStore()
        return _STORE_INSTANCE
