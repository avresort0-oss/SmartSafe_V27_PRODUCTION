"""
Leadwave-style design tokens for SmartSafe.
Central source of truth for colors, typography sizes, spacing, radius, and motion.
"""

from __future__ import annotations

from typing import Any, Dict


LIGHT_COLORS: Dict[str, str] = {
    # Surfaces
    "app_bg": "#F3F5FB",        # Subtle gray/indigo wash for app background
    "surface_1": "#FFFFFF",     # Primary card / content
    "surface_2": "#F1F4FF",     # Accented cards (KPIs, highlights)
    "surface_3": "#E2E8FF",     # Deepest surface / progress tracks
    "surface_hover": "#DCE7FF", # Hover / selection surface
    "border": "#D2DCF9",
    "border_strong": "#B3C1F5",
    # Text
    "text_primary": "#111827",
    "text_secondary": "#4B5563",
    "text_muted": "#6B7280",
    "text_inverse": "#FFFFFF",
    # Brand + semantic
    "brand": "#3B82F6",         # Indigo/blue primary
    "brand_hover": "#2563EB",
    "brand_soft": "#E0EDFF",
    "success": "#10B981",
    "warning": "#F59E0B",
    "warning_hover": "#D97706",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "info": "#2563EB",
    # Utility
    "focus_ring": "#93C5FD",
    "divider": "#E5ECFF",
    # Shadow tokens are interpreted by components using borders/overlays.
    "shadow_soft": "#E0E7FF",
    "shadow_strong": "#C7D2FE",
}

DARK_COLORS: Dict[str, str] = {
    # Surfaces
    "app_bg": "#111827",
    "surface_1": "#1F2937",
    "surface_2": "#374151",
    "surface_3": "#111827",
    "surface_hover": "#4B5563",
    "border": "#374151",
    "border_strong": "#4B5563",
    # Text
    "text_primary": "#F9FAFB",
    "text_secondary": "#D1D5DB",
    "text_muted": "#9CA3AF",
    "text_inverse": "#FFFFFF",
    # Brand + semantic
    "brand": "#4F46E5",
    "brand_hover": "#4338CA",
    "brand_soft": "#3730A3",
    "success": "#10B981",
    "warning": "#F59E0B",
    "warning_hover": "#D97706",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "info": "#3B82F6",
    # Utility
    "focus_ring": "#93C5FD",
    "divider": "#374151",
    "shadow_soft": "#0B1220",
    "shadow_strong": "#000000",
}

# Active palette (mutated in-place by theme manager; do not rebind).
COLORS: Dict[str, str] = dict(LIGHT_COLORS)


TYPOGRAPHY: Dict[str, Any] = {
    # Prefer a modern UI font; gracefully falls back via font_manager.
    "font_family": "Inter",
    # Slightly larger premium dashboard hierarchy
    "display": 30,
    "h1": 24,
    "h2": 20,
    "h3": 16,
    "body": 13,
    "caption": 11,
    # Monospace text size used by log/console-style widgets.
    # Several tabs expect this key (e.g. multi-account, analytics, balancer).
    "mono": 11,
}


SPACING: Dict[str, int] = {
    "xxs": 4,
    "xs": 8,
    "sm": 12,
    "md": 16,
    "lg": 24,
    "xl": 32,
}


RADIUS: Dict[str, int] = {
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
}


MOTION_MS: Dict[str, int] = {
    "quick": 120,
    "normal": 180,
    "slow": 220,
}


def semantic_from_text(text: str) -> str:
    """
    Infer a semantic button style from control text.
    Used as a non-breaking, best-effort styling aid for legacy tabs.
    """
    t = (text or "").strip().lower()

    # Common abbreviations used in compact icon-like buttons.
    if t in {"del"}:
        return "danger"
    if any(key in t for key in ("delete", "clear", "remove", "stop", "logout", "error", "failed")):
        return "danger"
    if any(key in t for key in ("check", "warning", "alert", "pause")):
        return "warning"
    if any(key in t for key in ("refresh", "retry", "sync", "load", "import")):
        return "secondary"
    if any(key in t for key in ("save", "start", "send", "connect", "run", "apply")):
        return "primary"
    return "secondary"
