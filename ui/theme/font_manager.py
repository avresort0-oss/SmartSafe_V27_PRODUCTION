"""
Font management utilities for Leadwave-style SmartSafe UI.

Tk does not reliably register TTF files directly at runtime on all platforms.
This module picks the best available installed family and provides consistent
font tuple helpers with graceful fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

from .design_tokens import TYPOGRAPHY


_CACHED_FAMILIES: Optional[set[str]] = None


def _primary_font() -> str:
    return (TYPOGRAPHY.get("font_family") or "Segoe UI").strip() or "Segoe UI"


def _heading_stack(primary: str) -> Sequence[str]:
    return (primary, "Sora", "Manrope", "Inter", "Segoe UI", "Arial")


def _body_stack(primary: str) -> Sequence[str]:
    return (primary, "Manrope", "Inter", "Segoe UI", "Arial")


MONO_STACK = ("Cascadia Mono", "Consolas", "Courier New")


def _load_system_families() -> set[str]:
    global _CACHED_FAMILIES
    if _CACHED_FAMILIES is not None:
        return _CACHED_FAMILIES

    families: set[str] = set()
    try:
        # Lazy import: avoids hard dependency during module import.
        import tkinter as tk
        from tkinter import font as tkfont

        # Never create a temporary hidden root here. Doing so can interfere with
        # window activation behavior on some Windows environments.
        root = tk._default_root
        if root is None:
            # Root not created yet: don't cache an empty set, re-attempt later.
            return set()

        families = {name for name in tkfont.families(root)}
    except Exception:
        families = set()

    _CACHED_FAMILIES = families
    return families


def pick_font(preferred_stack: Sequence[str], fallback: str = "Arial") -> str:
    families = _load_system_families()
    for name in preferred_stack:
        if name in families:
            return name
    return fallback


def heading(size: int, weight: str = "bold") -> Tuple[str, int, str]:
    primary = _primary_font()
    return (pick_font(_heading_stack(primary), fallback=primary), size, weight)


def body(size: int, weight: str = "normal") -> Tuple[str, int, str]:
    primary = _primary_font()
    return (pick_font(_body_stack(primary), fallback=primary), size, weight)


def mono(size: int, weight: str = "normal") -> Tuple[str, int, str]:
    return (pick_font(MONO_STACK, fallback="Consolas"), size, weight)


def bundled_fonts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "fonts"


def list_bundled_fonts() -> Iterable[Path]:
    font_dir = bundled_fonts_dir()
    if not font_dir.exists():
        return []
    return sorted(
        [*font_dir.glob("*.ttf"), *font_dir.glob("*.otf")]
    )


def _register_font_windows(path: Path) -> bool:
    """Try to register a font file for the current process on Windows.

    Returns True on success. This uses AddFontResourceExW with the
    FR_PRIVATE flag so the font is available to the current process only.
    """
    try:
        import ctypes
        FR_PRIVATE = 0x10
        AddFontResourceEx = ctypes.windll.gdi32.AddFontResourceExW
        res = AddFontResourceEx(str(path), FR_PRIVATE, 0)
        return bool(res)
    except Exception:
        return False


def register_bundled_fonts() -> list[Path]:
    """Best-effort register bundled font files so they become available to Tk.

    - On Windows this attempts to register fonts via the GDI API for the
      lifetime of the process.
    - On other platforms this is a no-op (font discovery is platform-specific).

    Returns the list of font files that were (likely) registered.
    """
    registered: list[Path] = []
    fonts = list_bundled_fonts()
    if not fonts:
        return registered

    import platform

    if platform.system() == "Windows":
        for f in fonts:
            if _register_font_windows(f):
                registered.append(f)
    else:
        # Non-Windows: leave fonts on-disk and rely on system availability.
        # Optionally, apps may call fc-cache or similar outside Python.
        registered = fonts

    # Reset cached family list so callers see newly-available families.
    global _CACHED_FAMILIES
    _CACHED_FAMILIES = None
    try:
        _load_system_families()
    except Exception:
        pass

    return registered


def preferred_font_family() -> str:
    """Return the best available primary font family (bundled or system).

    This prefers the configured `font_family` token but falls back to a
    discovered system font from the stacks.
    """
    primary = _primary_font()
    families = _load_system_families()
    if not families:
        return primary
    # If primary is available, return it; otherwise pick from stack.
    if primary in families:
        return primary
    return pick_font(_body_stack(primary), fallback=primary)
