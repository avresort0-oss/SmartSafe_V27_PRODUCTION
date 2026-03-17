from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "settings.json"


def read_settings_json() -> Dict[str, Any]:
    try:
        if not _SETTINGS_PATH.exists():
            return {}
        with _SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def write_settings_json(data: Dict[str, Any]) -> None:
    settings_dir = _SETTINGS_PATH.parent
    settings_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = _SETTINGS_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    os.replace(tmp_path, _SETTINGS_PATH)

