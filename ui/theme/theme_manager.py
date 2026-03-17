from __future__ import annotations

from typing import Literal, cast

import customtkinter as ctk

from ui.utils import user_settings

from .design_tokens import COLORS, DARK_COLORS, LIGHT_COLORS
from .leadwave_components import apply_leadwave_theme


ThemeName = Literal["dark", "light"]


def _normalize_theme(theme: str | None) -> ThemeName:
    t = (theme or "").strip().lower()
    if t in {"light", "l"}:
        return "light"
    return "dark"


def load_theme_from_settings() -> ThemeName:
    data = user_settings.read_settings_json()
    return _normalize_theme(cast(str | None, data.get("ui_theme")))


def save_theme_to_settings(theme: str) -> None:
    normalized = _normalize_theme(theme)
    data = user_settings.read_settings_json()
    data["ui_theme"] = normalized
    user_settings.write_settings_json(data)


def apply_theme(root: ctk.CTk, theme: str) -> ThemeName:
    """
    Apply palette + appearance mode.

    Safe to call before the UI is fully built; will best-effort restyle the shell
    and currently visible tab if available.
    """
    normalized = _normalize_theme(theme)

    palette = DARK_COLORS if normalized == "dark" else LIGHT_COLORS
    COLORS.clear()
    COLORS.update(palette)

    mode = "Dark" if normalized == "dark" else "Light"
    try:
        ctk.set_appearance_mode(mode)
    except Exception:
        pass
    try:
        ctk.set_default_color_theme("blue")
    except Exception:
        pass

    # Shell background
    try:
        root.configure(fg_color=COLORS["app_bg"])
    except Exception:
        pass

    # Let the shell do its own targeted recolor (keeps its corner radii intact).
    apply_shell_theme = getattr(root, "_apply_shell_theme", None)
    if callable(apply_shell_theme):
        try:
            apply_shell_theme()
        except Exception:
            pass

    # Best-effort re-theme the currently visible tab.
    tab_frame = None
    try:
        current_tab = getattr(root, "current_tab", None)
        tab_frames = getattr(root, "tab_frames", None)
        if current_tab and isinstance(tab_frames, dict):
            tab_frame = tab_frames.get(current_tab)
    except Exception:
        tab_frame = None

    if tab_frame is not None:
        try:
            apply_leadwave_theme(tab_frame)
        except Exception:
            pass

    return normalized

