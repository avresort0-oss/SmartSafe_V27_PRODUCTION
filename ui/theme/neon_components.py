import customtkinter as ctk
from .design_tokens import COLORS, RADIUS, TYPOGRAPHY
from . import font_manager

class GlassFrame(ctk.CTkFrame):
    """Simple glass-style frame for SmartSafe V26 FULL READY."""
    def __init__(self, master=None, **kwargs):
        base_kwargs = {
            "fg_color": COLORS["surface_1"],
            "corner_radius": RADIUS["lg"],
            "border_width": kwargs.pop("border_width", 1),
            "border_color": kwargs.pop("border_color", COLORS["border"]),
        }
        base_kwargs.update(kwargs)
        super().__init__(master, **base_kwargs)
        
        # Create inner frame for content
        self.inner_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.inner_frame.pack(fill="both", expand=True, padx=2, pady=2)


class NeonBorderFrame(ctk.CTkFrame):
    """Compatibility frame with Leadwave-safe defaults."""
    def __init__(self, master=None, border=2, **kwargs):
        base_kwargs = {
            "fg_color": COLORS["surface_2"],
            "corner_radius": RADIUS["md"],
            "border_width": border,
            "border_color": COLORS["border_strong"],
        }
        base_kwargs.update(kwargs)
        super().__init__(master, **base_kwargs)
        
        # Create inner frame for content
        self.inner_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.inner_frame.pack(fill="both", expand=True, padx=5, pady=5)


class NeonHeading(ctk.CTkLabel):
    """Compatibility heading with Leadwave-safe defaults."""
    def __init__(self, master=None, text="", **kwargs):
        base_kwargs = {
            "text": text,
            "font": font_manager.heading(TYPOGRAPHY["h1"], "bold"),
            "text_color": COLORS["text_primary"],
        }
        base_kwargs.update(kwargs)
        super().__init__(master, **base_kwargs)


class NeonLabel(ctk.CTkLabel):
    """Compatibility label with Leadwave-safe defaults."""
    def __init__(self, master=None, text="", **kwargs):
        base_kwargs = {
            "text": text,
            "font": font_manager.body(TYPOGRAPHY["body"]),
            "text_color": COLORS["text_primary"],
        }
        base_kwargs.update(kwargs)
        super().__init__(master, **base_kwargs)


def apply_neon_theme(widget):
    """Lightweight hook: keep for backwards compatibility.
    Currently no-op, but can be extended for global styling.
    """
    # For now we don't recursively recolor children to keep it simple/stable.
    return


class NeonButton(ctk.CTkButton):
    """Compatibility button with Leadwave-safe defaults."""
    def __init__(self, master, text="", command=None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            corner_radius=RADIUS["md"],
            height=38,
            fg_color=kwargs.pop("fg_color", COLORS["brand"]),
            hover_color=kwargs.pop("hover_color", COLORS["brand_hover"]),
            border_width=kwargs.pop("border_width", 1),
            border_color=kwargs.pop("border_color", COLORS["border_strong"]),
            text_color=kwargs.pop("text_color", COLORS["text_inverse"]),
            **kwargs
        )
