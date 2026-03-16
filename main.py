"""
SmartSafe V27 - PRODUCTION READY
100% Stable Multi-Account WhatsApp Automation System
Enhanced with comprehensive error handling and deployment features.

See `PROJECT_OVERVIEW.md` and `DEVELOPER_GUIDE.md` for a high-level overview
of how the UI shell in this module talks to the engine and Node/Baileys layers.
"""

import sys
import os

# --- DEPENDENCY CHECK START ---
def _check_dependencies():
    """
    Best-effort import check for core runtime and analytics/ML libraries.

    This is intentionally lightweight and defers detailed environment
    diagnostics to `verify_system.py`.
    """
    required = [
        # (pip_name, import_name)
        ("customtkinter", "customtkinter"),
        ("requests", "requests"),
        ("Pillow", "PIL"),
        ("qrcode", "qrcode"),
        ("openpyxl", "openpyxl"),
        ("pandas", "pandas"),
        ("python-dotenv", "dotenv"),
        ("scikit-learn", "sklearn"),
        ("numpy", "numpy"),
    ]

    missing = []
    for pip_name, import_name in required:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print("=" * 60)
        print(f"CRITICAL ERROR: Missing {len(missing)} required libraries.")
        print(f"Missing (pip names): {', '.join(sorted(set(missing)))}")
        print("-" * 60)
        print("PLEASE RUN: python verify_system.py")
        print("or install dependencies via: pip install -r requirements.txt")
        print("=" * 60)
        input("Press Enter to exit...")
        sys.exit(1)


_check_dependencies()
# --- DEPENDENCY CHECK END ---

import customtkinter as ctk
import logging
from datetime import datetime
import threading
from pathlib import Path
from tkinter import messagebox as tk_messagebox

from PIL import Image

from core.config import SETTINGS
from ui.theme import COLORS, RADIUS, SPACING, TYPOGRAPHY, body, heading, tab_icon_key, icon_path
from ui.theme.icon_registry import load_icon
from ui.theme.font_manager import register_bundled_fonts
from ui.theme import theme_manager
from ui.theme.leadwave_components import (
    AppShellHeader,
    StyledInput,
    StyledTabContainer,
    apply_leadwave_theme,
    harmonize_tab_spacing,
    configure_global_appearance,
)

def _configure_console_output():
    """
    Make console output tolerant on Windows code pages (e.g. cp1252).
    Unsupported characters are replaced instead of raising UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except Exception:
                pass


def _safe_console_print(text: str):
    """Best-effort print that never crashes on encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sanitized = str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(sanitized)


_configure_console_output()

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"smartsafe_{datetime.now().strftime('%Y%m%d')}.log"

# File handler with UTF-8 encoding
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Console handler with ASCII-safe formatting (no emojis)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

def start_webhook_server():
    """Starts the FastAPI webhook server in a background thread if enabled."""
    if SETTINGS.webhook_api_enabled:
        try:
            import uvicorn
            from core.api.webhook_server import app

            host = SETTINGS.webhook_api_host
            port = SETTINGS.webhook_api_port

            def run():
                logger.info(f"Starting Webhook API server on http://{host}:{port}")
                uvicorn.run(app, host=host, port=port)

            threading.Thread(target=run, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to start Webhook API server: {e}")

class SmartSafeProduction(ctk.CTk):
    """Production-ready SmartSafe with enhanced stability"""
    
    def __init__(self):
        super().__init__()

        # Load and apply persisted UI theme early (before building widgets).
        self.ui_theme = theme_manager.load_theme_from_settings()
        theme_manager.apply_theme(self, self.ui_theme)
        # Best-effort register bundled fonts so preferred fonts appear in Tk.
        try:
            registered = register_bundled_fonts()
            if registered:
                logger.info(f"Registered bundled fonts: {', '.join(str(p.name) for p in registered)}")
        except Exception:
            pass
        try:
            ctk.set_widget_scaling(1.0)
        except Exception:
            pass

        
        # Window configuration
        self.title("SmartSafe V27 - Professional Business Solution")
        self.geometry("1460x860")
        self.minsize(1200, 720)
        self.configure(fg_color=COLORS["app_bg"])
        
        # Full screen mode
        self.state("zoomed")
        
        # Prevent window close without confirmation
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize state
        self.tabs_loaded = {}
        self.active_processes = []
        self.tab_frames = {}
        self.tab_buttons = {}
        self.notification_counts = {}
        self.current_tab = None
        self.sidebar_collapsed = False
        self.animation_in_progress = False
        self._tab_icon_cache = {}
        # Performance optimizations
        self._nav_cache = {}
        self._all_tabs_preloaded = False
        self._tab_switch_token = 0
        
        # Create UI
        self.create_ui()
        
        # Load tabs with error recovery
        self.load_all_tabs()

        # Select first tab
        if self._get_tabs_config():
            self.select_tab(self._get_tabs_config()[0][0])

        # Force visible/focused startup window on Windows desktop environments.
        self.after(120, self._ensure_window_visible)
        
        logger.info("SmartSafe V27 Production initialized successfully")

    def _ensure_window_visible(self):
        """Best-effort bring-to-front for cases where Tk starts off-screen/minimized."""
        try:
            self.state("normal")
        except Exception:
            pass
        try:
            self.deiconify()
        except Exception:
            pass
        try:
            sw = int(self.winfo_screenwidth())
            sh = int(self.winfo_screenheight())
            w = max(1200, int(self.winfo_width() or 1460))
            h = max(720, int(self.winfo_height() or 860))
            w = min(w, sw)
            h = min(h, sh)
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        try:
            # Briefly topmost to avoid opening behind other windows.
            self.attributes("-topmost", True)
            self.after(350, lambda: self.attributes("-topmost", False))
        except Exception:
            pass
    
    def create_ui(self):
        """Create main UI structure"""
        self.header = AppShellHeader(
            self,
            title="SmartSafe V27",
            subtitle="Professional Business Solution",
            height=84,
        )
        self.header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        self.status_label = self.header.status_badge
        
        # Body container
        self.body_container = ctk.CTkFrame(self, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True, padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]))
        
        # Sidebar - Premium Ultra Style
        # mimic original LeadWave sidebar width and look
        self.sidebar = ctk.CTkFrame(
            self.body_container,
            width=250,  # Increased to fit full tab names
            fg_color="#FFFFFF",  # always white like LeadWave
            corner_radius=RADIUS["xl"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self.sidebar.pack(side="left", fill="y", padx=(0, SPACING["xs"]))
        self.sidebar.pack_propagate(False)
        
        # Sidebar branding header uses the application background color
        # (dark when the UI is in dark mode) so the logo/text can be light.
        branding_container = ctk.CTkFrame(self.sidebar, fg_color=COLORS["app_bg"], corner_radius=RADIUS["xl"])
        branding_container.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        
        branding_frame = ctk.CTkFrame(branding_container, fg_color="transparent", height=70)
        branding_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["sm"])
        branding_frame.grid_columnconfigure(0, weight=1)

        self.brand_label_frame = ctk.CTkFrame(branding_frame, fg_color="transparent")
        self.brand_label_frame.grid(row=0, column=0, sticky="w")
        
        # attempt to load a colour logo; falls back gracefully
        # sharp, premium appearance: a larger icon is used for branding.
        try:
            # load a slightly larger icon (48x48) for a sharp, premium appearance.
            # The user can replace brand.png with a high-quality SVG so it scales cleanly.
            sidebar_brand_img = load_icon("brand", size=(48, 48))

            sidebar_brand_icon = ctk.CTkImage(
                light_image=sidebar_brand_img,
                dark_image=sidebar_brand_img,
                size=(48, 48),
            )
        except Exception:
            sidebar_brand_icon = None

        # replace previous single label with icon-on-top layout
        # ensure there is no stray text when the image is missing
        self.brand_icon_label = ctk.CTkLabel(
            self.brand_label_frame,
            text="",                  # explicitly empty
            image=sidebar_brand_icon,
            fg_color="transparent",
        )
        self.brand_icon_label.pack(side="top", pady=(0, SPACING["xs"]))

        # convert the logo text into a stylized image so it always looks
        # premium (gradient fill + subtle shadow) rather than a plain label
        def _make_logo_text(text: str, size: int):
            from PIL import ImageDraw, ImageFont

            font_path = None

            font = ImageFont.truetype(font_path or "arial.ttf", size)
            # measure text
            left, top, right, bottom = font.getbbox(text)
            w = right - left
            h = bottom - top
            
            img = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # shadow
            draw.text((4, 4), text, font=font, fill=(0, 0, 0, 100))
            # gradient fill
            for i, char in enumerate(text):
                # simple left-to-right gradient
                x = int(font.getlength(text[:i]))
                char_w = int(font.getlength(char))
                grad = Image.new("RGBA", (char_w, h), (0, 0, 0, 0))
                grad_draw = ImageDraw.Draw(grad)
                r1, g1, b1 = (69, 65, 255)  # start colour (violet)
                r2, g2, b2 = (59, 130, 246)  # end colour (blue)
                for y0 in range(h):
                    t = y0 / h if h > 0 else 0
                    r = int(r1 + (r2 - r1) * t)
                    g = int(g1 + (g2 - g1) * t)
                    b = int(b1 + (b2 - b1) * t)
                    grad_draw.line([(0, y0), (char_w, y0)], fill=(r, g, b))
                img.paste(grad, (x, 0), grad)
            return img

        logo_text_img = None
        try:
            logo_text_img = _make_logo_text("SmartSafe", TYPOGRAPHY["display"])
            logo_text_icon = ctk.CTkImage(light_image=logo_text_img, dark_image=logo_text_img)
        except Exception:
            logo_text_icon = None

        if logo_text_icon:
            self.brand_title_label = ctk.CTkLabel(
                self.brand_label_frame,
                image=logo_text_icon,
                text="",
                fg_color="transparent",
            )
        else:
            self.brand_title_label = ctk.CTkLabel(
                self.brand_label_frame,
                text="SmartSafe",
                font=heading(TYPOGRAPHY["display"], "bold"),
                text_color=COLORS["brand"],
                anchor="w"
            )
        self.brand_title_label.pack(side="top", anchor="w")

        self.brand_subtitle_label = ctk.CTkLabel(
            self.brand_label_frame,
            text="Professional Business Solution",
            font=body(TYPOGRAPHY["caption"], "italic"),
            text_color=COLORS["text_inverse"],
            anchor="w",
            wraplength=160,
        )
        self.brand_subtitle_label.pack(side="top", fill="x", pady=(SPACING["xxs"], 0))

        self.collapse_btn = ctk.CTkButton(
            branding_frame,
            text="<",
            width=32,
            height=32,
            corner_radius=RADIUS["md"],
            fg_color=COLORS["brand_soft"],
            hover_color=COLORS["brand"],
            text_color=COLORS["brand"],
            font=body(14, "bold"),
            command=self.toggle_sidebar
        )
        self.collapse_btn.grid(row=0, column=1, sticky="e", padx=(SPACING["xs"], 0))

        # Divider Line
        divider = ctk.CTkFrame(self.sidebar, fg_color=COLORS["border"], height=2)
        divider.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        # Navigation Container (Ultra Premium Scrollable) with explicit white background
        self.nav_container = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="#FFFFFF",  # always white, regardless of theme mode
            corner_radius=RADIUS["lg"],
            width=180,
        )
        self.nav_container.pack(fill="both", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        try:
            self.nav_container.configure(
                scrollbar_fg_color="transparent",
                scrollbar_button_color=COLORS["surface_2"],
                scrollbar_button_hover_color=COLORS["surface_hover"],
                scrollbar_corner_radius=RADIUS["md"],
            )
        except Exception:
            pass
        
        # Content Area
        self.content_area = ctk.CTkFrame(
            self.body_container,
            fg_color=COLORS["surface_1"],
            corner_radius=RADIUS["xl"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self.content_area.pack(side="right", fill="both", expand=True)

        # Loading Frame (for async tab loading)
        self.loading_frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        loading_container = ctk.CTkFrame(self.loading_frame, fg_color="transparent")
        loading_container.pack(expand=True)
        ctk.CTkLabel(
            loading_container,
            text="Loading Module...",
            font=heading(TYPOGRAPHY["h1"], "bold"),
            text_color=COLORS["text_muted"],
        ).pack(pady=(0, SPACING["lg"]))
        self.loading_progress = ctk.CTkProgressBar(loading_container, width=200)
        self.loading_progress.pack()
        self.loading_progress.configure(mode="indeterminate")
        self.loading_progress.start()
        try:
            self.loading_progress.configure(
                fg_color=COLORS["surface_3"],
                progress_color=COLORS["brand"],
                border_color=COLORS["border"],
            )
        except Exception:
            pass
        
        # Sidebar footer removed (version label not needed)
        # previous version label and footer intentionally omitted to match clean look
        pass

        # Ensure shell widgets match the active theme tokens.
        self._apply_shell_theme()

    def set_notification_badge(self, tab_name: str, count: int):
        """Update notification badge for a specific tab"""
        self.notification_counts[tab_name] = count
        self._render_nav()

    def _set_status(self, text: str, tone: str = "info"):
        self.header.set_status(text, tone=tone)

    def _on_theme_change(self, value: str):
        desired = "dark" if str(value).strip().lower() == "dark" else "light"
        if desired == getattr(self, "ui_theme", "dark"):
            return # Early Exit

        self.ui_theme = desired
        try:
            theme_manager.save_theme_to_settings(desired)
        except Exception:
            pass
        theme_manager.apply_theme(self, desired)

        # Re-theme any already-loaded tabs (theme_manager only targets the active tab).
        try:
            for state in getattr(self, "tabs_loaded", {}).values():
                if not isinstance(state, dict) or state.get("status") != "loaded": # Guard
                    continue
                inst = state.get("instance")
                if inst is not None:
                    apply_leadwave_theme(inst)
        except Exception:
            pass

    def _apply_shell_theme(self) -> None:
        """Recolor shell widgets based on current design tokens."""
        try:
            self.configure(fg_color=COLORS["app_bg"])
        except Exception:
            pass

        # Header
        try:
            self.header.configure(fg_color=COLORS["surface_1"], border_color=COLORS["border"])
            self.header.title_label.configure(text_color=COLORS["text_primary"])
            self.header.subtitle_label.configure(text_color=COLORS["text_secondary"])
        except Exception:
            pass

        # Main containers
        try:
            self.sidebar.configure(fg_color=COLORS["surface_1"], border_color=COLORS["border"])
        except Exception:
            pass
        try:
            self.nav_container.configure(fg_color="transparent")
        except Exception:
            pass
        try:
            self.content_area.configure(fg_color=COLORS["surface_1"], border_color=COLORS["border"])
        except Exception:
            pass
        try:
            self.loading_progress.configure(
                fg_color=COLORS["surface_3"],
                progress_color=COLORS["brand"],
                border_color=COLORS["border"],
            )
        except Exception:
            pass

        # Branding + controls
        try:
            # keep header text light when using dark app background
            self.brand_title_label.configure(text_color=COLORS["text_inverse"])
            self.brand_subtitle_label.configure(text_color=COLORS["text_inverse"])
        except Exception:
            pass
        try:
            self.collapse_btn.configure(
                fg_color=COLORS["surface_2"],
                hover_color=COLORS["surface_hover"],
                text_color=COLORS["text_primary"],
            )
        except Exception:
            pass

        # Footer
        try:
            self.footer.configure(
                fg_color=COLORS.get("surface_1", "#FFFFFF"),
                border_color=COLORS.get("border", "#000000"),
            )
            self.footer_label.configure(
                text_color=COLORS.get("text_secondary", "#666666")
            )
        except Exception:
            pass

        # Refresh navigation styles
        try:
            self._render_nav()
        except Exception:
            pass
    
    def _get_tabs_config(self):
        """Get tab configuration sorted by priority."""
        config = [
            # Dashboard (Priority 0)
            ("Dashboard", "ui.tabs.dashboard_tab", "DashboardTab", 0),
            
            # Core tabs (Priority 1)
            ("QR Login", "ui.tabs.qr_login_tab", "QRLoginTab", 1),
            ("Multi-Account", "ui.tabs.multi_account_panel_tab", "MultiAccountPanelTab", 1),
            
            # Main engines (Priority 2)
            ("Single Engine", "ui.tabs.send_engine_tab", "SendEngineTab", 2),
            ("Multi Engine", "ui.tabs.multi_engine_tab", "MultiEngineTab", 2),
            ("Bulk Sender", "ui.tabs.bulk_sender_pro_tab", "BulkSenderProTab", 2),
            
            # Tools (Priority 3)
            ("Templates", "ui.tabs.template_manager_tab", "TemplateManagerTab", 3),
            ("Balancer", "ui.tabs.balancer_tab", "BalancerTab", 3),
            ("Formatter", "ui.tabs.bulk_formatter_tab", "BulkFormatterTab", 3),
            ("Profile Check", "ui.tabs.profile_checker_tab", "ProfileCheckerTab", 3),
            
            ("OTP Sender", "ui.tabs.otp_sender_tab", "OTPSenderTab", 4),
            ("Analytics", "ui.tabs.analytics_pro_tab", "AnalyticsProTab", 4),
            ("ML Analytics", "ui.tabs.ml_analytics_tab", "MLAnalyticsTab", 4),
            ("Message Tracking", "ui.tabs.message_tracking_tab", "MessageTrackingTab", 4),
            ("Settings", "ui.tabs.settings_tab", "SettingsTab", 4),
            ("Spam Dashboard", "ui.tabs.spam_dashboard_tab", "SpamDashboardTab", 4),
            ("Flow Builder", "ui.tabs.flow_builder_tab", "FlowBuilderTab", 5),
        ]
        
        # Enable all tabs by default (Fixed: No longer hidden)
        config.extend(
            [
                ("Auto-Reply", "ui.tabs.autoreply_tab", "AutoReplyTab", 4),
                ("Cloud Sync", "ui.tabs.cloud_sync_tab", "CloudSyncTab", 4),
            ]
        )
        
        return sorted(config, key=lambda x: x[3])

    def _get_tab_icon(self, name):
        """Return icon for tab name. Uses more compatible Unicode symbols."""
        icons = {
            "Dashboard": "⌂",      # House
            "QR Login": "▣",       # Square with small square
            "Multi-Account": "👥",  # Busts in Silhouette
            "Single Engine": "▶",    # Play
            "Multi Engine": "⏩",   # Fast-forward
            "Bulk Sender": "✉",      # Envelope
            "Templates": "📄",      # Page
            "Balancer": "⇆",       # Arrows
            "Formatter": "¶",      # Pilcrow
            "Profile Check": "👤",    # Bust
            "OTP Sender": "🔑",      # Key
            "Analytics": "📈",      # Chart
            "ML Analytics": "🧠",   # Brain
            "Message Tracking": "📊", # Bar chart
            "Auto-Reply": "↩",     # Arrow with hook
            "Cloud Sync": "☁",       # Cloud
            "Settings": "🛠️",       # Hammer and Wrench
            "Flow Builder": "⚙️"     # Gear
        }
        return icons.get(name, "•")

    def _get_tab_icon_image(self, label: str, tint: str | None = None):
        """Return a CTkImage for *label* optionally tinted to a specific color.

        Tinting is used so that icons can switch between primary and inverse
        foregrounds depending on the button state. The cache key includes the
        tint value so we don't recolor the same icon repeatedly.
        """
        key = tab_icon_key(label)
        cache_key = (key, tint)
        cached = self._tab_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            pil = load_icon(key, size=(20, 20))
        except Exception:
            try:
                pil = load_icon("brand", size=(20, 20))
            except Exception:
                pil = Image.new("RGBA", (20, 20), (0, 0, 0, 0))

        # apply tint by recoloring non-transparent pixels
        if tint:
            try:
                r, g, b = self.winfo_rgb(tint)
                # winfo_rgb returns 16-bit channel values; normalize to 0-255
                r, g, b = (int(x / 256) for x in (r, g, b))
                tinted = Image.new("RGBA", pil.size, (r, g, b, 0))
                mask = pil.split()[3]  # alpha channel
                pil = Image.composite(tinted, pil, mask)
            except Exception:
                pass

        icon = ctk.CTkImage(light_image=pil, dark_image=pil, size=(20, 20))
        self._tab_icon_cache[cache_key] = icon
        return icon

    def toggle_sidebar(self):
        if self.animation_in_progress:
            return
            
        self.sidebar_collapsed = not self.sidebar_collapsed
        
        start_width = self.sidebar.winfo_width()
        end_width = 88 if self.sidebar_collapsed else 250
        
        self._animate_sidebar(start_width, end_width)

    def _animate_sidebar(self, start, end):
        self.animation_in_progress = True
        steps = 10  # Reduced from 15 to 10 for better performance
        delay = 12  # Increased from 10ms to 12ms to reduce CPU load

        def _animate(step):
            if step > steps:
                self.sidebar.configure(width=end)
                self.animation_in_progress = False
                # Show content after expanding
                if not self.sidebar_collapsed:
                    self._update_sidebar_content_visibility()
                return

            progress = step / steps
            # Ease in-out
            p = progress * progress * (3 - 2 * progress)
            
            current_width = int(start + (end - start) * p)
            self.sidebar.configure(width=current_width)
            
            self.after(delay, lambda: _animate(step + 1))
        
        # Hide content before starting animation if collapsing
        if self.sidebar_collapsed:
            self._update_sidebar_content_visibility()

        _animate(0)

    def _update_sidebar_content_visibility(self):
        is_collapsed = self.sidebar_collapsed
        
        self.collapse_btn.configure(text=">" if is_collapsed else "<")
        
        if is_collapsed:
            self.brand_label_frame.grid_forget()
        else:
            self.brand_label_frame.grid(row=0, column=0, sticky="w")  # Fixed
        self._render_nav()
    def _render_nav(self):
        """
        Render navigation safely.

        We rebuild every time instead of reusing cached Tk widgets because
        destroyed widget references are not reusable and can leave the sidebar
        empty during rapid tab switching.
        """
        # Clear existing for rebuild
        for widget in self.nav_container.winfo_children():
            try:
                widget.destroy()
            except AttributeError:
                # Workaround for customtkinter CTkButton destroy() bug with _font attribute
                pass

        try:
            self.tab_buttons.clear()
        except Exception:
            pass
        
        # Build new navigation
        for tab_name, _, _, _priority in self._get_tabs_config():
            self._create_nav_button(tab_name)

        # Keep this cache empty; widget-object caching is unsafe for Tk.
        try:
            self._nav_cache.clear()
        except Exception:
            pass
    
    def _create_nav_button(self, tab_name):
        """Create a single navigation button"""
        # compute active state early so styling can be derived
        is_active = (self.current_tab == tab_name)
        fg = COLORS["brand_soft"] if is_active else "transparent"
        hover = COLORS["brand_soft"] if is_active else COLORS["surface_hover"]
        text_c = COLORS["text_inverse"] if is_active else COLORS["text_primary"]
        font_s = body(TYPOGRAPHY["body"], "bold" if is_active else "normal")

        # decide on icon: prefer unicode glyphs (more reliable) and display
        unicode_icon = self._get_tab_icon(tab_name)
        btn_text = "" if self.sidebar_collapsed else f"{unicode_icon}  {tab_name}"
        btn_anchor = "center" if self.sidebar_collapsed else "w"

        # Container for button and badge - Premium style
        btn_container = ctk.CTkFrame(self.nav_container, fg_color="transparent")
        btn_container.pack(
            fill="x",
            padx=SPACING["sm"],
            pady=SPACING["xs"],
        )
        btn_container._tab_name = tab_name  # Store tab name for caching
        
        if self.sidebar_collapsed:
            # collapsed icons-only state using unicode glyph
            btn_kwargs = {
                "text": unicode_icon,
                "height": 56,
                "width": 64,
                "fg_color": fg,
                "text_color": text_c,
                "hover_color": hover,
                "anchor": "center",
                "font": font_s,
                "corner_radius": RADIUS["lg"],
                "border_width": 0,
                "command": lambda t=tab_name: self.select_tab(t),
            }
            btn = ctk.CTkButton(btn_container, **btn_kwargs)
            btn.pack(fill="x", pady=2)
            self.tab_buttons[tab_name] = btn
            return btn_container

        btn_container.grid_columnconfigure(0, weight=1)

        # simplified active styling: full-bleed brand background
        btn_kwargs = {
            "text": btn_text,
            # no image when using unicode icons
            "compound": "left",
            "height": 48,
            "fg_color": COLORS["brand"] if is_active else "transparent",
            "text_color": COLORS["text_inverse"] if is_active else COLORS["text_primary"],
            "hover_color": COLORS["brand_hover"] if is_active else COLORS["surface_hover"],
            "anchor": btn_anchor,
            "font": font_s,
            "corner_radius": RADIUS["lg"],
            "border_width": 0,
            "command": lambda t=tab_name: self.select_tab(t),
        }
        btn = ctk.CTkButton(btn_container, **btn_kwargs)
        btn.grid(row=0, column=0, sticky="ew", pady=2)
        self.tab_buttons[tab_name] = btn

        count = self.notification_counts.get(tab_name, 0)
        if count > 0:
            badge_text = str(count) if count < 100 else "99+"
            badge = ctk.CTkLabel(
                btn_container,
                text=badge_text,
                fg_color=COLORS["danger"],
                text_color=COLORS["text_inverse"],
                height=22,
                width=26,
                corner_radius=12,
                font=body(10, "bold"),
            )
            badge.grid(row=0, column=2, sticky="e", padx=(SPACING["xs"], 0))
        
        return btn_container

    def load_all_tabs(self):
        """Load tabs with lazy loading support and preload all tabs"""
        self.tab_configs = {t[0]: t for t in self._get_tabs_config()}
        
        # Initial render of navigation
        self._render_nav()
        
        # Preload all tabs in background for better UX
        if not self._all_tabs_preloaded:
            self._preload_all_tabs()
            self._all_tabs_preloaded = True
            
        self._set_status("Ready", tone="success")
    
    def _preload_all_tabs(self):
        """Preload all tabs in the background for instant switching."""
        from ui.utils.threading_helpers import start_daemon
        
        def _preload_worker():
            # Preload all tabs so that when the user clicks them, they appear instantly.
            all_tabs = [tab[0] for tab in self._get_tabs_config()]
            for tab_name in all_tabs:
                try:
                    if tab_name not in self.tabs_loaded:
                        # Add delay between preloads to reduce system load
                        import time
                        time.sleep(0.1)
                        self._load_single_tab_background(tab_name)
                        logger.info(f"Preloaded tab: {tab_name}")
                except Exception as e:
                    logger.warning(f"Failed to preload {tab_name}: {e}")
                    # Continue with other tabs even if one fails
                    continue
        
        start_daemon(_preload_worker)

    def select_tab(self, tab_name):
        """Handle tab selection with improved robustness and animation."""
        if self.current_tab == tab_name:
            return

        self._tab_switch_token += 1
        switch_token = self._tab_switch_token
        
        # Set the new tab as current
        self.current_tab = tab_name
        
        # Log current state for debugging
        logger.info(f"Selected tab: {tab_name}")
        
        # Rerender the navigation. This is the source of truth for button styles.
        self._render_nav()

        # If tab is already loaded, just show it with animation
        if tab_name in self.tabs_loaded and self.tabs_loaded[tab_name]["status"] == "loaded":
            # Hide all other tab frames before showing the new one
            for frame in self.tab_frames.values():
                frame.pack_forget()
                frame.place_forget()
            self._animate_frame_in(self.tab_frames[tab_name])
            return

        # If not loaded yet, keep the previous tab visible and load the new
        # one in the background. When ready, we'll switch instantly without
        # showing a blocking "Loading Module" screen.
        self.after(50, lambda t=tab_name, tok=switch_token: self._load_and_display_tab(t, tok))

    def _load_and_display_tab(self, tab_name, switch_token=None):
        """Loads tab content asynchronously to prevent UI freeze."""
        from ui.utils.threading_helpers import start_daemon, ui_dispatch
        
        def background_load():
            try:
                # Do the heavy lifting in background thread
                self._load_single_tab_background(tab_name)
                
                # Update UI in main thread
                def _update_ui():
                    if switch_token is not None and switch_token != self._tab_switch_token:
                        return
                    if tab_name != self.current_tab:
                        return
                    
                    # Check if loaded with error and render error view if needed
                    state = self.tabs_loaded.get(tab_name, {})
                    if state.get("status") == "error":
                        self._render_tab_error(tab_name, state.get("error", "Unknown Error"))

                    if tab_name in self.tab_frames:
                        # Hide all other tab frames before showing the new one
                        for frame in self.tab_frames.values():
                            frame.pack_forget()
                            frame.place_forget()
                        self._animate_frame_in(self.tab_frames[tab_name])
                        
                        if state.get("status") == "error":
                            self._set_status("Error", tone="danger")
                        else:
                            self._set_status("Ready", tone="success")
                
                ui_dispatch(self, _update_ui)
            except Exception as e:
                def _show_error():
                    self._set_status(f"Error loading {tab_name}", tone="danger")
                    self._render_tab_error(tab_name, str(e))
                
                ui_dispatch(self, _show_error)
        
        # Start background loading
        start_daemon(background_load)

    def _animate_frame_in(self, new_frame):
        """
        Show a newly loaded tab frame.

        Animations look nice but can make the UI feel sluggish on
        lower-spec machines. To keep the interface responsive, we
        simply pack the frame without transitional effects.
        """
        try:
            self.content_area.pack_propagate(False)
        except Exception:
            pass

        # Directly show the frame without incremental animation.
        try:
            new_frame.place_forget()
        except Exception:
            pass
        new_frame.pack(fill="both", expand=True)

    def _load_single_tab_background(self, tab_name):
        """Load tab content in background thread"""
        from ui.utils.threading_helpers import ui_dispatch
        
        if tab_name in self.tabs_loaded and self.tabs_loaded[tab_name]["status"] == "loaded":
            return

        cfg = self.tab_configs.get(tab_name)
        if not cfg:
            return

        _, module_path, class_name, _ = cfg
        
        try:
            # Dynamic import in background
            logger.info(f"Background loading tab: {tab_name}")
            module = __import__(module_path, fromlist=[class_name])
            tab_class = getattr(module, class_name)

            # Create frame and instance in UI thread
            def _create_ui(_tab_name=tab_name, _tab_class=tab_class):
                try:
                    # Create frame if not exists
                    if _tab_name not in self.tab_frames:
                        self.tab_frames[_tab_name] = ctk.CTkFrame(self.content_area, fg_color="transparent")
                    
                    tab_frame = self.tab_frames[_tab_name]
                    
                    # Clear any existing content
                    for widget in tab_frame.winfo_children():
                        widget.destroy()
                    
                    # Create container
                    container = StyledTabContainer(tab_frame)
                    container.pack(fill="both", expand=True, padx=SPACING["xxs"], pady=SPACING["xxs"])
                    
                    # Initialize
                    tab_instance = _tab_class(container)
                    tab_instance.pack(fill="both", expand=True)
                    
                    # Apply theme with error handling
                    try:
                        apply_leadwave_theme(tab_instance)
                    except Exception as theme_error:
                        logger.warning(f"Theme application failed for {_tab_name}: {theme_error}")
                    
                    try:
                        harmonize_tab_spacing(tab_instance)
                    except Exception as spacing_error:
                        logger.warning(f"Tab spacing failed for {_tab_name}: {spacing_error}")
                    
                    self.tabs_loaded[_tab_name] = {
                        "instance": tab_instance,
                        "status": "loaded"
                    }
                    logger.info(f"[OK] Loaded: {_tab_name}")
                    
                except Exception as ui_error:
                    logger.error(f"UI creation failed for {_tab_name}: {ui_error}")
                    # Mark as failed but don't crash
                    self.tabs_loaded[_tab_name] = {
                        "status": "error", 
                        "error": str(ui_error)
                    }
            
            ui_dispatch(self, _create_ui)
            
        except Exception as e:
            logger.error(f"Failed to load {tab_name}: {e}")
            # Don't raise - let the system handle gracefully
            # Store error state for UI to display
            def _store_error():
                self.tabs_loaded[tab_name] = {
                    "status": "error", 
                    "error": str(e)
                }
            
            ui_dispatch(self, _store_error)

    def _render_tab_error(self, tab_name, error_msg):
        """Render error state within the tab"""
        self.tabs_loaded[tab_name] = {"status": "error", "error": error_msg}
        
        # Ensure frame exists
        if tab_name not in self.tab_frames:
            self.tab_frames[tab_name] = ctk.CTkFrame(self.content_area, fg_color="transparent")
            
        tab_frame = self.tab_frames[tab_name]
        for widget in tab_frame.winfo_children():
            widget.destroy()
            
        error_container = ctk.CTkFrame(
            tab_frame,
            fg_color=COLORS["surface_1"],
            corner_radius=RADIUS["lg"],
            border_width=1,
            border_color=COLORS["danger"],
        )
        error_container.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        
        ctk.CTkLabel(
            error_container,
            text=f"Error Loading {tab_name}",
            font=heading(TYPOGRAPHY["h2"], "bold"),
            text_color=COLORS["danger"],
        ).pack(pady=(SPACING["lg"], SPACING["xs"]))
        
        error_text = ctk.CTkTextbox(
            error_container,
            height=200,
            fg_color=COLORS["surface_2"],
            text_color=COLORS["text_primary"],
        )
        error_text.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["xs"])
        error_text.insert("1.0", error_msg)
        error_text.configure(state="disabled")
        
        ctk.CTkButton(
            error_container,
            text="Retry Loading",
            command=lambda: self.retry_load_tab(tab_name),
            height=40,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger"],
        ).pack(pady=SPACING["lg"])

    def retry_load_tab(self, tab_name):
        """Retry loading a failed tab"""
        logger.info(f"Retrying load for: {tab_name}")
        cfg = self.tab_configs.get(tab_name)
        if cfg:
            import importlib
            import sys
            module_path = cfg[1]
            if module_path in sys.modules:
                try:
                    importlib.reload(sys.modules[module_path])
                except Exception:
                    pass
            self._load_and_display_tab(tab_name)
    
    def on_closing(self):
        """Handle window close event"""
        # Check for active processes
        if any(self.active_processes):
            if not self._confirm_exit_with_fallback():
                return
        
        logger.info("Application closing...")
        
        # Cleanup
        try:
            # Stop any running processes
            for process in self.active_processes:
                if hasattr(process, 'stop'):
                    process.stop()
            
            # Save state if needed
            self.save_state()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
        
        # Close application
        logger.info("Application closed successfully")
        self.destroy()

    def _confirm_exit_with_fallback(self) -> bool:
        """Use tkinter messagebox for exit confirmation."""
        prompt = "Active processes are running. Are you sure you want to exit?"

        return bool(tk_messagebox.askyesno("Confirm Exit", prompt))
    
    def save_state(self):
        """Save application state"""
        try:
            # Implement state saving if needed
            pass
        except Exception as e:
            logger.error(f"Error saving state: {str(e)}")


def main():
    """Main entry point with error handling"""
    try:
        logger.info("=" * 60) # Corrected spacing and added brackets
        logger.info("SmartSafe V27 Production Starting...")
        logger.info(f"Python Version: {sys.version}")
        logger.info(f"Working Directory: {os.getcwd()}") # type: ignore
        logger.info("=" * 60)
        
        # Start background services like the Webhook API
        start_webhook_server()

        # Create and run application
        app = SmartSafeProduction()
        logger.info("[OK] Application initialized successfully")
        logger.info("[START] Starting main loop...")
        
        app.mainloop()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (Ctrl+C)")
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.critical(f"CRITICAL ERROR: {str(e)}")
        logger.critical(f"TRACEBACK:\n{tb}")
        # Also display a message box to the user
        try:
            # Use a simpler tkinter messagebox as CTk might be part of the problem
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Critical Error",
                "A critical error occurred. Please check the logs for more details.\\n\\n"
                f"Error: {e}"
            )
        except Exception as msg_e:
            # Fallback to console if GUI fails
            _safe_console_print(f"CRITICAL ERROR: {e}")
            _safe_console_print(f"Could not display GUI error message: {msg_e}")
        
        # Finally, exit
        sys.exit(1)

if __name__ == "__main__":
    main()
