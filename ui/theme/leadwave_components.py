"""
Leadwave-style reusable UI components and non-breaking global theming helpers.
Premium edition with micro-interactions, smooth transitions, and visual depth.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from PIL import Image
import threading
import time

from .design_tokens import COLORS, RADIUS, SPACING, TYPOGRAPHY, semantic_from_text, MOTION_MS
from . import font_manager
from .icon_registry import icon_path, load_icon


def configure_global_appearance(mode: str | None = None) -> None:
    """
    Configure CustomTkinter global appearance.

    If `mode` is provided ("Light", "Dark", or "System"), it sets the global
    appearance mode. The default color theme is kept as "blue" since SmartSafe
    primarily uses token-driven colors.
    """
    if mode:
        try:
            ctk.set_appearance_mode(mode)
        except Exception:
            pass
    ctk.set_default_color_theme("blue")


def _safe_configure(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


class AppShellHeader(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(
            master,
            fg_color=COLORS["surface_1"],
            corner_radius=RADIUS["xl"],
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)

        self.brand_icon = None
        try:
            brand_img = load_icon("brand", size=(20, 20))
            self.brand_icon = ctk.CTkImage(light_image=brand_img, dark_image=brand_img, size=(20, 20))
        except Exception:
            self.brand_icon = None

        self.title_label = ctk.CTkLabel(
            left,
            text=title,
            image=self.brand_icon,
            compound="left",
            font=font_manager.heading(TYPOGRAPHY["h1"], weight="bold"),
            text_color=COLORS["text_primary"],
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            left,
            text=subtitle,
            font=font_manager.body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_secondary"],
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=16, pady=12)

        self.status_badge = StatusBadge(right, text="READY", tone="success")
        self.status_badge.pack()

    def set_status(self, text: str, tone: str = "info") -> None:
        self.status_badge.set_text(text, tone=tone)


class SectionCard(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        self._is_hovered = False
        self._base_border_color = kwargs.pop("border_color", COLORS["border"])
        
        super().__init__(
            master,
            fg_color=kwargs.pop("fg_color", COLORS["surface_1"]),
            corner_radius=kwargs.pop("corner_radius", RADIUS["lg"]),
            border_width=kwargs.pop("border_width", 1),
            border_color=self._base_border_color,
            **kwargs,
        )
        self.inner_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.inner_frame.pack(
            fill="both",
            expand=True,
            padx=SPACING["md"],
            pady=SPACING["md"],
        )
        
        # Premium micro-interaction: hover effect
        self.bind("<Enter>", self._on_hover_enter)
        self.bind("<Leave>", self._on_hover_leave)
    
    def _on_hover_enter(self, event=None):
        self._is_hovered = True
        try:
            self.configure(border_color=COLORS.get("border_strong", COLORS["border"]))
        except Exception:
            pass
    
    def _on_hover_leave(self, event=None):
        self._is_hovered = False
        try:
            self.configure(border_color=self._base_border_color)
        except Exception:
            pass


class StatCard(SectionCard):
    def __init__(self, master, label: str, value: str = "0", tone: str = "info", **kwargs):
        kwargs.setdefault("fg_color", COLORS.get("surface_2", COLORS["surface_1"]))
        kwargs.setdefault("border_color", COLORS.get("border_strong", COLORS["border"]))
        kwargs.setdefault("corner_radius", RADIUS["lg"])
        super().__init__(master, **kwargs)
        color = _tone_color(tone)
        self._value_color = color
        self.label = ctk.CTkLabel(
            self.inner_frame,
            text=label,
            font=font_manager.body(TYPOGRAPHY["caption"], weight="normal"),
            text_color=COLORS["text_secondary"],
        )
        self.label.pack(anchor="w")
        self.value = ctk.CTkLabel(
            self.inner_frame,
            text=value,
            font=font_manager.heading(TYPOGRAPHY["h1"], weight="bold"),
            text_color=color,
        )
        self.value.pack(anchor="w", pady=(4, 0))

    def set_value(self, value: str, animate: bool = False) -> None:
        self.value.configure(text=value, text_color=self._value_color)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text: str, command=None, **kwargs):
        super().__init__(
            master,
            width=kwargs.pop("width", 120),
            text=text,
            command=command,
            height=kwargs.pop("height", 44),
            corner_radius=kwargs.pop("corner_radius", RADIUS["lg"]),
            fg_color=kwargs.pop("fg_color", COLORS["brand"]),
            hover_color=kwargs.pop("hover_color", COLORS["brand_hover"]),
            text_color=kwargs.pop("text_color", COLORS["text_inverse"]),
            border_width=kwargs.pop("border_width", 0),
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["body"], weight="bold")),
            **kwargs,
        )


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, text: str, command=None, **kwargs):
        super().__init__(
            master,
            width=kwargs.pop("width", 120),
            text=text,
            command=command,
            height=kwargs.pop("height", 44),
            corner_radius=kwargs.pop("corner_radius", RADIUS["lg"]),
            fg_color=kwargs.pop("fg_color", COLORS.get("surface_2", COLORS["surface_1"])),
            hover_color=kwargs.pop("hover_color", COLORS.get("surface_hover", COLORS["surface_1"])),
            text_color=kwargs.pop("text_color", COLORS["text_primary"]),
            border_width=kwargs.pop("border_width", 1),
            border_color=kwargs.pop("border_color", COLORS.get("border_strong", COLORS["border"])),
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["body"], weight="bold")),
            **kwargs,
        )


class StatusBadge(ctk.CTkLabel):
    def __init__(self, master, text: str, tone: str = "info", pulse: bool = False, **kwargs):
        color = _tone_color(tone)
        self._pulse = pulse
        self._is_pulsing = False
        self._pulse_colors = [color, COLORS.get(color + "_soft", color)]
        
        super().__init__(
            master,
            text=text,
            corner_radius=kwargs.pop("corner_radius", RADIUS["md"]),
            fg_color=kwargs.pop("fg_color", color),
            text_color=kwargs.pop("text_color", COLORS["text_inverse"]),
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["caption"], weight="bold")),
            padx=SPACING["md"],
            pady=SPACING["xs"],
            **kwargs,
        )
        
        if self._pulse and text.upper() == "LIVE":
            self._start_pulse()

    def set_text(self, text: str, tone: str = "info", pulse: bool = False) -> None:
        color = _tone_color(tone)
        self.configure(text=text, fg_color=color)
        self._pulse = pulse
        if self._pulse and text.upper() == "LIVE":
            self._start_pulse()
        else:
            self._is_pulsing = False
    
    def _start_pulse(self):
        if self._is_pulsing:
            return
        self._is_pulsing = True
        self._pulse_animation()
    
    def _pulse_animation(self):
        if not self._is_pulsing or not self.winfo_exists():
            return
        try:
            color1 = self._pulse_colors[0]
            def pulse():
                try:
                    self.configure(fg_color=color1)
                    self.after(MOTION_MS["normal"], lambda: self.winfo_exists() and self._pulse_animation())
                except Exception:
                    pass
            pulse()
        except Exception:
            pass


class StyledInput(ctk.CTkEntry):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=kwargs.pop("corner_radius", RADIUS["md"]),
            fg_color=kwargs.pop("fg_color", COLORS["surface_1"]),
            border_width=kwargs.pop("border_width", 2),
            border_color=kwargs.pop("border_color", COLORS.get("border_subtle", COLORS["border"])),
            text_color=kwargs.pop("text_color", COLORS["text_primary"]),
            placeholder_text_color=kwargs.pop("placeholder_text_color", COLORS["text_muted"]),
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["body"])),
            **kwargs,
        )
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
    
    def _on_focus_in(self, event=None):
        try:
            self.configure(border_color=COLORS["focus_ring"])
        except Exception:
            pass
    
    def _on_focus_out(self, event=None):
        try:
            self.configure(border_color=COLORS.get("border_subtle", COLORS["border"]))
        except Exception:
            pass


class StyledTextbox(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=kwargs.pop("corner_radius", RADIUS["md"]),
            fg_color=kwargs.pop("fg_color", COLORS["surface_1"]),
            border_width=kwargs.pop("border_width", 1),
            border_color=kwargs.pop("border_color", COLORS["border"]),
            text_color=kwargs.pop("text_color", COLORS["text_primary"]),
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["body"])),
            **kwargs,
        )


class StyledTabContainer(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=kwargs.pop("fg_color", "transparent"),
            **kwargs,
        )


class TitleLabel(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text,
            font=kwargs.pop("font", font_manager.heading(TYPOGRAPHY["h2"], "bold")),
            text_color=kwargs.pop("text_color", COLORS["text_primary"]),
            **kwargs,
        )

class BodyLabel(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text,
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["body"])),
            text_color=kwargs.pop("text_color", COLORS["text_secondary"]),
            **kwargs,
        )

class CaptionLabel(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text,
            font=kwargs.pop("font", font_manager.body(TYPOGRAPHY["caption"])),
            text_color=kwargs.pop("text_color", COLORS["text_muted"]),
            **kwargs,
        )


class TabHeader(ctk.CTkFrame):
    """
    Standard tab header row with title/subtitle on the left and an actions
    container on the right.

    Usage:
        header = TabHeader(root, title="Analytics PRO", subtitle="Live insights")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        PrimaryButton(header.actions, text="Refresh", command=...)
    """

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(fill="x")

        TitleLabel(title_row, text=title).pack(side="left", anchor="w")
        if subtitle:
            CaptionLabel(title_row, text=subtitle).pack(
                side="left",
                anchor="w",
                padx=(SPACING["xs"], 0),
            )

        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.grid(row=0, column=1, sticky="e")


class StatsRow(ctk.CTkFrame):
    """
    Standard KPI row composed of multiple StatCard instances.

    Usage:
        stats = StatsRow(root)
        stats.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        total_card = stats.add_stat("Total Messages", "0", tone="info")
        errors_card = stats.add_stat("Errors", "0", tone="danger")
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure("all", weight=1)
        self._next_col = 0

    def add_stat(self, label: str, value: str = "0", tone: str = "info") -> StatCard:
        col = self._next_col
        self._next_col += 1

        card = StatCard(self, label=label, value=value, tone=tone)
        card.grid(row=0, column=col, sticky="ew", padx=SPACING["xs"])
        return card


class ContentSection(SectionCard):
    """
    SectionCard with a built-in title/subtitle header and a content container.

    Usage:
        section = ContentSection(root, title="Per-Account Stats")
        section.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        table = StyledTextbox(section.content, ...)
        table.pack(fill="both", expand=True)
    """

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, **kwargs)

        header = ctk.CTkFrame(self.inner_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, SPACING["sm"]))

        TitleLabel(header, text=title).pack(side="left", anchor="w")
        if subtitle:
            CaptionLabel(header, text=subtitle).pack(side="left", padx=(SPACING["xs"], 0))

        self.content = ctk.CTkFrame(self.inner_frame, fg_color="transparent")
        self.content.pack(fill="both", expand=True)


def _tone_color(tone: str) -> str:
    t = (tone or "").lower()
    if t == "success":
        return COLORS["success"]
    if t == "warning":
        return COLORS["warning"]
    if t == "danger":
        return COLORS["danger"]
    return COLORS["info"]


def _frame_color_for_depth(depth: int) -> str:
    if depth <= 0:
        return COLORS["surface_1"]
    if depth % 2:
        return COLORS["surface_2"]
    return COLORS["surface_1"]


def apply_leadwave_theme(widget, depth: int = 0) -> None:
    """
    Non-breaking recursive theming for legacy tabs.
    Keeps behavior untouched while improving visual consistency.
    """
    # Top-level dialogs (CTkToplevel) need an explicit background; otherwise they
    # keep the default theme color and look disconnected from the app shell.
    if isinstance(widget, ctk.CTkToplevel):
        _safe_configure(widget, fg_color=COLORS["surface_1"])

    # Standard Tk widgets occasionally appear inside CTk UIs (e.g. Canvas).
    if isinstance(widget, tk.Canvas):
        try:
            widget.configure(bg=COLORS["surface_2"])
        except Exception:
            pass

    # Frame-like containers
    if isinstance(widget, ctk.CTkFrame) and not isinstance(
        widget,
        (AppShellHeader, SectionCard, StatCard, TabHeader, StatsRow, ContentSection),
    ):
        color = widget.cget("fg_color")
        if color not in ("transparent", None):
            _safe_configure(
                widget,
                fg_color=_frame_color_for_depth(depth),
                border_color=COLORS["border"],
                corner_radius=RADIUS["md"] if depth > 0 else RADIUS["lg"],
            )

        # If this looks like a top-level tab/frame (depth 0), apply balanced
        # spacing between immediate children to improve visual flow without
        # changing internal layouts.
        if isinstance(widget, ctk.CTkFrame) and depth == 0:
            try:
                harmonize_tab_spacing(widget)
            except Exception:
                pass

    if isinstance(widget, ctk.CTkLabel) and not isinstance(widget, (TitleLabel, BodyLabel, CaptionLabel, StatusBadge)):
        current = (widget.cget("text_color") or "")
        fg = None
        try:
            fg = widget.cget("fg_color")
        except Exception:
            fg = None

        fg_is_transparent = fg in ("transparent", None, "")
        if isinstance(fg, (tuple, list)) and fg:
            fg_is_transparent = all(item in ("transparent", None, "") for item in fg)

        text = (widget.cget("text") or "").strip()
        # Only normalize "white" labels when they sit on transparent backgrounds.
        # Pills/badges often use white text on colored backgrounds, and those
        # should keep high-contrast inverse text.
        if fg_is_transparent and current in ("", "white", "#ffffff", "#FFFFFF"):
            _safe_configure(widget, text_color=COLORS["text_primary"])

        # Preserve explicit heading-sized fonts; only harmonize "regular" labels.
        should_adjust_font = True
        try:
            existing_font = widget.cget("font")
            if isinstance(existing_font, (tuple, list)) and len(existing_font) >= 2:
                size = int(existing_font[1])
                if size > int(TYPOGRAPHY["body"]):
                    should_adjust_font = False
        except Exception:
            should_adjust_font = True

        if should_adjust_font:
            if text and len(text) <= 40:
                _safe_configure(widget, font=font_manager.body(TYPOGRAPHY["body"]))
            else:
                _safe_configure(widget, font=font_manager.body(TYPOGRAPHY["caption"]))

    if isinstance(widget, ctk.CTkButton) and not isinstance(widget, (PrimaryButton, SecondaryButton)):
        semantic = semantic_from_text(str(widget.cget("text") or ""))
        if semantic == "primary":
            _safe_configure(
                widget,
                fg_color=COLORS["brand"],
                hover_color=COLORS["brand_hover"],
                text_color=COLORS["text_inverse"],
            )
        elif semantic == "danger":
            _safe_configure(
                widget,
                fg_color=COLORS["danger"],
                hover_color=COLORS["danger_hover"],
                text_color=COLORS["text_inverse"],
            )
        elif semantic == "warning":
            _safe_configure(
                widget,
                fg_color=COLORS["warning"],
                hover_color=COLORS["warning_hover"],
                text_color=COLORS["text_inverse"],
            )
        else:
            _safe_configure(
                widget,
                fg_color=COLORS["surface_2"],
                hover_color=COLORS["surface_hover"],
                border_width=1,
                border_color=COLORS["border_strong"],
                text_color=COLORS["text_primary"],
            )
        _safe_configure(widget, corner_radius=RADIUS["md"], font=font_manager.body(TYPOGRAPHY["body"], "bold"))

    if isinstance(widget, ctk.CTkEntry):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_1"],
            border_width=1,
            border_color=COLORS["border_strong"],
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            corner_radius=RADIUS["md"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkCheckBox):
        _safe_configure(
            widget,
            text_color=COLORS["text_primary"],
            fg_color=COLORS["brand"],
            hover_color=COLORS["brand_hover"],
            border_color=COLORS["border_strong"],
            checkmark_color=COLORS["text_inverse"],
            corner_radius=RADIUS["sm"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkSwitch):
        existing_progress = ""
        try:
            existing_progress = str(widget.cget("progress_color") or "")
        except Exception:
            existing_progress = ""

        keep_progress = existing_progress in {
            str(COLORS.get("success", "")),
            str(COLORS.get("warning", "")),
            str(COLORS.get("danger", "")),
            str(COLORS.get("info", "")),
        }
        _safe_configure(
            widget,
            text_color=COLORS["text_primary"],
            progress_color=(existing_progress if keep_progress else COLORS["brand"]),
            button_color=COLORS["surface_1"],
            button_hover_color=COLORS["surface_2"],
            fg_color=COLORS["surface_3"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkTextbox):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_1"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=RADIUS["md"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkProgressBar):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_3"],
            progress_color=COLORS["brand"],
            border_color=COLORS["border"],
            corner_radius=RADIUS["sm"],
        )

    if isinstance(widget, ctk.CTkComboBox):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_1"],
            button_color=COLORS["surface_2"],
            button_hover_color=COLORS["surface_hover"],
            border_color=COLORS["border_strong"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_1"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text_primary"],
            corner_radius=RADIUS["md"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkOptionMenu):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_1"],
            button_color=COLORS["surface_2"],
            button_hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface_1"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text_primary"],
            corner_radius=RADIUS["md"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkRadioButton):
        _safe_configure(
            widget,
            text_color=COLORS["text_primary"],
            fg_color=COLORS["brand"],
            hover_color=COLORS["brand_hover"],
            border_color=COLORS["border_strong"],
            font=font_manager.body(TYPOGRAPHY["body"]),
        )

    if isinstance(widget, ctk.CTkSegmentedButton):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_2"],
            selected_color=COLORS["brand"],
            selected_hover_color=COLORS["brand_hover"],
            unselected_color=COLORS["surface_2"],
            unselected_hover_color=COLORS["surface_hover"],
            text_color=COLORS["text_primary"],
            text_color_disabled=COLORS["text_muted"],
            font=font_manager.body(TYPOGRAPHY["caption"], "bold"),
            corner_radius=RADIUS["md"],
        )

    if isinstance(widget, ctk.CTkScrollableFrame):
        _safe_configure(
            widget,
            fg_color=COLORS["surface_1"],
            border_color=COLORS["border"],
            corner_radius=RADIUS["md"],
            scrollbar_fg_color="transparent",
            scrollbar_button_color=COLORS["surface_2"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )

    children = getattr(widget, "winfo_children", lambda: [])()
    for child in children:
        apply_leadwave_theme(child, depth=depth + 1)


def harmonize_tab_spacing(tab_root) -> None:
    """
    Apply balanced spacing to first-level children in a tab root.
    This is intentionally conservative to avoid breaking existing layouts.
    """
    children = getattr(tab_root, "winfo_children", lambda: [])()
    for child in children:
        manager = ""
        try:
            manager = child.winfo_manager()
        except Exception:
            manager = ""

        if manager == "pack":
            try:
                info = child.pack_info()
                padx = info.get("padx", 0)
                pady = info.get("pady", 0)
                if str(padx) in ("0", ""):
                    child.pack_configure(padx=SPACING["xs"])
                if str(pady) in ("0", ""):
                    child.pack_configure(pady=max(4, int(SPACING["xxs"]) + 2))
            except Exception:
                pass

        if manager == "grid":
            try:
                info = child.grid_info()
                padx = info.get("padx", 0)
                pady = info.get("pady", 0)
                if str(padx) in ("0", ""):
                    child.grid_configure(padx=SPACING["xs"])
                if str(pady) in ("0", ""):
                    child.grid_configure(pady=max(4, int(SPACING["xxs"]) + 2))
            except Exception:
                pass
