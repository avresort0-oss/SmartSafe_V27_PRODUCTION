"""
Icon registry for Leadwave-style SmartSafe UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple
import io
from PIL import Image

# Simple in-memory cache for resized icons to avoid repeated disk/resize work.
_ICON_CACHE: Dict[Tuple[str, Tuple[int, int]], Image.Image] = {}


ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"

ICONS: Dict[str, str] = {
    # the branding icon is special: if an SVG is dropped into the
    # assets/icons directory it will be preferred (svg support requires
    # cairosvg, which is optional). this allows designers to ship a
    # high‑resolution vector logo rather than a raster PNG.
    "brand": "brand.svg" if (ICON_DIR / "brand.svg").exists() else "brand.png",

    "qr": "qr.png",
    "accounts": "accounts.png",
    "single_send": "single_send.png",
    "multi_send": "multi_send.png",
    "bulk": "bulk.png",
    "templates": "templates.png",
    "balancer": "balancer.png",
    "formatter": "formatter.png",
    "profile": "profile.png",
    "otp": "otp.png",
    "autoreply": "autoreply.png",
    "analytics": "analytics.png",
    "warning": "warning.png",
    "error": "error.png",
    "success": "success.png",
    "refresh": "refresh.png",
}


TAB_ICON_KEY: Dict[str, str] = {
    # core tabs
    "Dashboard": "analytics",        # generic dashboard/chart icon
    "QR Login": "qr",
    "Multi-Account": "accounts",

    # engines
    "Single Engine": "single_send",
    "Multi Engine": "multi_send",
    "Bulk Sender": "bulk",

    # tools
    "Templates": "templates",
    "Balancer": "balancer",
    "Formatter": "formatter",
    "Profile Check": "profile",
    "OTP Sender": "otp",
    "Auto-Reply": "autoreply",
    "Cloud Sync": "refresh",

    # analytics & misc
    "Analytics": "analytics",
    "ML Analytics": "analytics",
    "Message Tracking": "analytics",
    "Settings": "settings",
}


def icon_path(name: str) -> Path:
    filename = ICONS.get(name)
    if not filename:
        return ICON_DIR / "brand.png"
    return ICON_DIR / filename


def load_icon(name: str, size: tuple[int, int] = (20, 20)) -> Image.Image:
    """
    Load and return a PIL Image for the requested icon sized to `size`.

    Behavior:
    - Uses an in-memory cache keyed by `(name, size)`.
    - Supports PNG (and SVG if `cairosvg` is installed).
    - Falls back to a transparent placeholder if the file is missing or fails to decode.
    """
    key = (name, (int(size[0]), int(size[1])))
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    p = icon_path(name)
    if p.exists():
        try:
            suffix = p.suffix.lower()
            if suffix == ".svg":
                try:
                    import cairosvg

                    png_bytes = cairosvg.svg2png(url=str(p), output_width=key[1][0], output_height=key[1][1])
                    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                    _ICON_CACHE[key] = img
                    return img
                except Exception:
                    # Fall back to raster handling below if cairosvg not available
                    pass

            # Raster handling (PNG, JPG, etc.)
            img = Image.open(p).convert("RGBA")
            img = img.resize(key[1], Image.LANCZOS)
            _ICON_CACHE[key] = img
            return img
        except Exception:
            pass

    # Fallback: transparent placeholder to avoid crashes when icon missing
    img = Image.new("RGBA", key[1], (0, 0, 0, 0))
    _ICON_CACHE[key] = img
    return img


def tab_icon_key(label: str) -> str:
    return TAB_ICON_KEY.get(label, "brand")
