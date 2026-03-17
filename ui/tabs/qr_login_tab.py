import customtkinter as ctk
from PIL import Image, ImageDraw
import qrcode
import io
import json
from datetime import datetime, timedelta
import threading
import base64
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

from core.api.whatsapp_baileys import BaileysAPI
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme.leadwave_components import apply_leadwave_theme
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    RADIUS,
    TabHeader,
    SectionCard,
    StatusBadge,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    heading,
    body,
)


class ConnectionStatus(Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting..."
    CONNECTED = "Connected"
    ERROR = "Error"
    EXPIRED = "Session Expired"


@dataclass
class AccountInfo:
    account_id: str
    phone_number: str
    device_name: str
    status: ConnectionStatus
    last_connected: Optional[datetime] = None
    qr_code_data: Optional[str] = None
    connection_attempts: int = 0
    max_retries: int = 3


class Tab(ctk.CTkFrame):
    def __init__(self, parent, on_account_change: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)

        self.configure(fg_color="transparent")
        self.on_account_change = on_account_change

        # API and data
        self.api = BaileysAPI()
        self.current_account: Optional[AccountInfo] = None
        self.accounts: dict = {}
        self.session_expires_at = datetime.now() + timedelta(minutes=10)
        self.status_poller_thread = None
        self.load_thread = None

        # Build Modern UI
        self._build_ui()

        # Apply theme
        apply_leadwave_theme(self)

        # Start background tasks
        self._start_background_tasks()

    def _start_background_tasks(self):
        """Start daemon threads for loading and polling"""
        # FIX: Initialize with fallback account for immediate QR display
        self.load_thread = start_daemon(self._load_accounts)
        self.status_poller_thread = start_daemon(self._status_poller)

    def _build_ui(self):
        """Build the modern UI layout"""
        # Header
        self.header = TabHeader(
            self,
            title="Link Device (QR)",
            subtitle="Scan the code to connect your WhatsApp account",
        )
        self.header.pack(
            fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"])
        )

        # Header Badge
        badge_colors = self._get_badge_colors_from_tone("neutral")
        self.header_status = StatusBadge(
            self.header.actions, text="Ready", **badge_colors
        )
        self.header_status.pack(side="right")

        # Main Grid Layout
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(
            fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"])
        )
        content.grid_columnconfigure(0, weight=2)  # QR side (wider)
        content.grid_columnconfigure(1, weight=1)  # Controls side
        content.grid_rowconfigure(0, weight=1)

        # --- Left Column: QR Code ---
        link_card = SectionCard(content)
        link_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]))

        # Mode switcher (QR vs Pairing Code)
        self.link_mode_var = ctk.StringVar(value="QR Code")
        link_mode_switch = ctk.CTkSegmentedButton(
            link_card.inner_frame,
            values=["QR Code", "Pairing Code"],
            variable=self.link_mode_var,
            command=self._on_link_mode_change,
        )
        link_mode_switch.pack(pady=(SPACING["sm"], SPACING["sm"]))

        # Container for swapping link methods
        self.link_method_container = ctk.CTkFrame(
            link_card.inner_frame, fg_color="transparent"
        )
        self.link_method_container.pack(fill="both", expand=True)

        # --- QR Code Frame (now inside link_method_container) ---
        self.qr_frame = ctk.CTkFrame(self.link_method_container, fg_color="transparent")
        self.qr_frame.pack(fill="both", expand=True)  # Shown by default

        ctk.CTkLabel(
            self.qr_frame,
            text="Scan with WhatsApp",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(pady=(0, 0))

        self.qr_container = ctk.CTkFrame(
            self.qr_frame,
            fg_color="white",
            corner_radius=RADIUS["lg"],
            width=300,
            height=300,
        )
        self.qr_container.pack(pady=SPACING["md"], padx=SPACING["lg"])
        self.qr_container.pack_propagate(False)

        self.qr_image_label = ctk.CTkLabel(
            self.qr_container,
            text="Initializing...",
            text_color="black",
            font=body(TYPOGRAPHY["body"]),
        )
        self.qr_image_label.place(relx=0.5, rely=0.5, anchor="center")

        self.session_label = ctk.CTkLabel(
            self.qr_frame,
            text="Session expires in 10:00",
            text_color=COLORS["text_secondary"],
            font=body(TYPOGRAPHY["caption"]),
        )
        self.session_label.pack(pady=(0, SPACING["md"]))

        # Instructions
        inst_frame = ctk.CTkFrame(
            self.qr_frame, fg_color=COLORS["surface_2"], corner_radius=RADIUS["md"]
        )
        inst_frame.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["lg"]))

        steps = [
            "1. Open WhatsApp on phone",
            "2. Menu > Linked Devices",
            "3. Tap 'Link a Device'",
            "4. Point camera at screen",
        ]
        for step in steps:
            ctk.CTkLabel(
                inst_frame,
                text=step,
                font=body(TYPOGRAPHY["body"]),
                text_color=COLORS["text_primary"],
                anchor="w",
            ).pack(fill="x", padx=SPACING["md"], pady=4)

        # --- Pairing Code Frame (NEW, inside link_method_container) ---
        self.pairing_code_frame = ctk.CTkFrame(
            self.link_method_container, fg_color="transparent"
        )
        # self.pairing_code_frame is hidden by default

        ctk.CTkLabel(
            self.pairing_code_frame,
            text="Enter this code on your phone",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(pady=(0, 0))

        # Manual Phone Input
        self.pairing_input_frame = ctk.CTkFrame(
            self.pairing_code_frame, fg_color="transparent"
        )
        self.pairing_input_frame.pack(pady=(SPACING["sm"], 0))
        ctk.CTkLabel(
            self.pairing_input_frame,
            text="Phone Number:",
            font=body(TYPOGRAPHY["caption"]),
        ).pack(side="left", padx=5)
        self.pairing_phone_entry = StyledInput(
            self.pairing_input_frame, width=180, placeholder_text="e.g. 1234567890"
        )
        self.pairing_phone_entry.pack(side="left")

        self.pairing_code_display = ctk.CTkLabel(
            self.pairing_code_frame,
            text="--- --- ---",
            font=heading(TYPOGRAPHY["display"], "bold"),
            text_color=COLORS["brand"],
            fg_color=COLORS["surface_2"],
            corner_radius=RADIUS["lg"],
            padx=SPACING["xl"],
            pady=SPACING["lg"],
        )
        self.pairing_code_display.pack(pady=SPACING["lg"])

        # Pairing Code Instructions
        pairing_inst_frame = ctk.CTkFrame(
            self.pairing_code_frame,
            fg_color=COLORS["surface_2"],
            corner_radius=RADIUS["md"],
        )
        pairing_inst_frame.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["lg"]))

        pairing_steps = [
            "1. Open WhatsApp on phone",
            "2. Menu > Linked Devices",
            "3. Tap 'Link a Device'",
            "4. Choose 'Link with phone number instead'",
            "5. Enter the code above",
        ]
        for step in pairing_steps:
            ctk.CTkLabel(
                pairing_inst_frame,
                text=step,
                font=body(TYPOGRAPHY["body"]),
                text_color=COLORS["text_primary"],
                anchor="w",
            ).pack(fill="x", padx=SPACING["md"], pady=4)

        # --- Right Column: Controls ---
        right_panel = ctk.CTkFrame(content, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")

        # Account Selection
        acc_card = SectionCard(right_panel)
        acc_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(
            acc_card.inner_frame,
            text="Active Account",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xs"]))
        self.accounts_container = ctk.CTkScrollableFrame(
            acc_card.inner_frame, height=140, fg_color="transparent"
        )
        self.accounts_container.pack(fill="x")

        # New Session Input
        new_frame = ctk.CTkFrame(acc_card.inner_frame, fg_color="transparent")
        new_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        ctk.CTkLabel(
            new_frame, text="New Session Name:", font=body(TYPOGRAPHY["caption"])
        ).pack(side="left", padx=(0, SPACING["xs"]))
        self.new_session_entry = StyledInput(
            new_frame, width=200, placeholder_text="e.g. my_new_session"
        )
        self.new_session_entry.pack(side="left", padx=(0, SPACING["xs"]))
        new_btn = SecondaryButton(
            new_frame, text="Create & Connect", command=self.create_new_session
        )
        new_btn.pack(side="right")

        # Connection Details
        info_card = SectionCard(right_panel)
        info_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(
            info_card.inner_frame,
            text="Status Details",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xs"]))
        self.info_labels = {}
        self._create_info_row(info_card.inner_frame, "Phone", "account_phone")
        self._create_info_row(info_card.inner_frame, "Device", "account_device")
        self._create_info_row(info_card.inner_frame, "Status", "account_status")

        # Actions
        action_card = SectionCard(right_panel)
        action_card.pack(fill="x")
        self.refresh_button = PrimaryButton(
            action_card.inner_frame, text="Refresh QR Code", command=self._on_refresh
        )
        self.refresh_button.pack(fill="x", pady=(0, SPACING["xs"]))
        self.save_qr_button = SecondaryButton(
            action_card.inner_frame, text="Save QR Image", command=self._on_save_qr
        )
        self.save_qr_button.pack(fill="x", pady=(0, SPACING["xs"]))
        SecondaryButton(
            action_card.inner_frame,
            text="Disconnect Session",
            command=self._on_disconnect,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color="white",
        ).pack(fill="x")

    def _on_link_mode_change(self, mode: str):
        """Switch between QR and Pairing Code views."""
        if mode == "QR Code":
            self.pairing_code_frame.pack_forget()
            self.qr_frame.pack(fill="both", expand=True)
            self.refresh_button.configure(text="Refresh QR Code")
            self.save_qr_button.configure(state="normal")
            self._refresh_qr_display()
        else:  # Pairing Code
            self.qr_frame.pack_forget()
            self.pairing_code_frame.pack(fill="both", expand=True)
            self.refresh_button.configure(text="Generate New Code")
            self.save_qr_button.configure(
                state="disabled"
            )  # Can't save a pairing code as image
            self._on_generate_pairing_code()

    def _on_refresh(self):
        """Generic refresh handler for the active link mode."""
        mode = self.link_mode_var.get()
        if mode == "QR Code":
            self._on_refresh_qr()
        else:
            self._on_generate_pairing_code()

    def _create_info_row(self, parent, label_text, key):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=2)
        ctk.CTkLabel(
            f,
            text=label_text,
            text_color=COLORS["text_secondary"],
            font=body(TYPOGRAPHY["body"]),
        ).pack(side="left")
        v = ctk.CTkLabel(
            f,
            text="-",
            text_color=COLORS["text_primary"],
            font=body(TYPOGRAPHY["body"], "bold"),
        )
        v.pack(side="right")
        self.info_labels[key] = v

    def _load_accounts(self):
        """Load real accounts from BaileysAPI + always add New Session option"""
        try:
            result = self.api.get_accounts()
            if not result.get("ok"):
                # Fallback: Use default account and show warning
                badge_colors = self._get_badge_colors_from_tone("warning")
                ui_dispatch(
                    self,
                    lambda: self.header_status.configure(
                        text="No Accounts", **badge_colors
                    ),
                )
                ui_dispatch(self, self._update_account_selector)
                return

            accounts_data = result.get("accounts", [])
            if not accounts_data:
                badge_colors = self._get_badge_colors_from_tone("info")
                ui_dispatch(
                    self,
                    lambda: self.header_status.configure(
                        text="No Config", **badge_colors
                    ),
                )
                return

            self.accounts = {}
            for acc_data in accounts_data:
                acc_id = acc_data.get("account", "unknown")
                phone = acc_data.get("number", "N/A")
                device = acc_data.get("device_name", f"Device {acc_id}")
                connected = acc_data.get("connected", False)
                status = (
                    ConnectionStatus.CONNECTED
                    if connected
                    else ConnectionStatus.DISCONNECTED
                )

                self.accounts[acc_id] = AccountInfo(
                    account_id=acc_id,
                    phone_number=phone,
                    device_name=device,
                    status=status,
                )

            # Always add New Session option (creates fresh if selected)
            self.accounts["new_session"] = AccountInfo(
                account_id="new_session",
                phone_number="Create Fresh Session",
                device_name="New QR Device",
                status=ConnectionStatus.DISCONNECTED,
            )

            ui_dispatch(self, self._update_account_selector)

            if self.accounts and list(self.accounts.keys())[0] != "default":
                first_id = list(self.accounts.keys())[0]
                ui_dispatch(self, lambda: self._load_account(first_id))

        except Exception as e:
            ui_dispatch(self, lambda: self._show_error(f"API error: {str(e)}"))
            ui_dispatch(self, self._update_account_selector)

    def _status_poller(self):
        """Poll status every 3 seconds"""
        while True:
            try:
                if self.current_account:
                    result = self.api.get_health(self.current_account.account_id)
                    if result.get("ok"):
                        connected = bool(result.get("connected"))
                        status = (
                            ConnectionStatus.CONNECTED
                            if connected
                            else ConnectionStatus.DISCONNECTED
                        )

                        self.current_account.status = status
                        ui_dispatch(self, self._update_status_display)
                threading.Event().wait(3)
            except Exception:
                pass

    def _update_account_selector(self):
        """Update account buttons from loaded accounts"""
        # Clear existing buttons
        for widget in self.accounts_container.winfo_children():
            widget.destroy()

        if not self.accounts:
            no_accounts_btn = SecondaryButton(
                self.accounts_container,
                text="No accounts configured",
                state="disabled",
                fg_color=COLORS["surface_2"],
            )
            no_accounts_btn.pack(fill="x", pady=2)
            return

        for acc_id, acc_info in self.accounts.items():
            self._create_account_button(self.accounts_container, acc_id, acc_info)

    def _create_account_button(self, parent, acc_id: str, acc_info: AccountInfo):
        """Create individual account button"""
        is_selected = self.current_account and self.current_account.account_id == acc_id
        bg_color = COLORS["brand"] if is_selected else COLORS["surface_2"]
        text_color = "white" if is_selected else COLORS["text_primary"]
        hover_color = COLORS["brand_hover"] if is_selected else COLORS["surface_hover"]

        btn = ctk.CTkButton(
            parent,
            text=f"{acc_info.phone_number} ({acc_info.status.value})",
            font=body(TYPOGRAPHY["body"]),
            height=40,
            fg_color=bg_color,
            hover_color=hover_color,
            text_color=text_color,
            anchor="w",
            corner_radius=RADIUS["md"],
            command=lambda: self._load_account(acc_id),
        )
        btn.pack(fill="x", pady=2)

    def _fetch_pairing_code(self, account_id: str):
        """
        Fetch pairing code from API.
        """
        # Get account info
        acc = self.accounts.get(account_id)
        if not acc:
            return {"ok": False, "error": "Account not found"}

        # For default/demo account, return a fake code
        if account_id == "default":
            return {"ok": True, "code": "DEMO-1234"}

        # Extract clean phone number
        phone = getattr(acc, "phone_number", "")
        clean_number = "".join(filter(str.isdigit, phone or ""))

        if not clean_number:
            return {
                "ok": False,
                "error": "Account must have a phone number to generate pairing code",
            }

        try:
            return self.api.get_pairing_code(account_id, clean_number)
        except Exception as e:
            print(f"Pairing code fetch error for {account_id}: {e}")
            return {"ok": False, "error": str(e)}

    def _fetch_qr(self, account_id: str):
        """Fetch REAL QR from API - no demo fakes"""
        try:
            if account_id.startswith("new_session"):
                # Auto-connect fresh session first
                connect_result = self.api.connect_account(account_id)
                if not connect_result.get("ok"):
                    print(
                        f"Connect failed for {account_id}: {connect_result.get('error')}"
                    )

            result = self.api.get_qr(account_id)
            if result.get("ok") and result.get("qr"):
                qr_data = result["qr"]
                # Handle base64 image
                if qr_data.startswith("data:image/"):
                    # Remove data URL prefix
                    qr_b64 = qr_data.split(",")[1]
                    img_data = base64.b64decode(qr_b64)
                    img = Image.open(io.BytesIO(img_data))
                    return img
                else:
                    # Raw base64 or QR text
                    img_data = base64.b64decode(qr_data)
                    img = Image.open(io.BytesIO(img_data))
                    return img
            else:
                print(f"No QR for {account_id}: {result}")
                return None
        except Exception as e:
            print(f"QR fetch error for {account_id}: {e}")
            return None

    def _load_account(self, acc_id: str):
        """Load account and display info"""
        if acc_id not in self.accounts:
            self.qr_image_label.configure(text="Account not found", image=None)
            return

        self.current_account = self.accounts[acc_id]

        # Set active account in API
        try:
            self.api.set_account(acc_id)
        except Exception:
            pass

        # Update UI
        self._update_status_display()
        self._refresh_qr_display()
        self._update_account_selector()  # Refresh buttons selection

        # Update info panels
        self.info_labels["account_phone"].configure(
            text=self.current_account.phone_number
        )
        self.info_labels["account_device"].configure(
            text=self.current_account.device_name
        )
        self.info_labels["account_status"].configure(
            text=self.current_account.status.value,
            text_color=self._get_status_color(self.current_account.status)[0],
        )

        # Reset session timer
        self.session_expires_at = datetime.now() + timedelta(minutes=10)
        self._update_session_timer()

        if self.on_account_change:
            self.on_account_change(acc_id)

    def create_new_session(self):
        """Create and connect fresh session with custom name."""
        name = self.new_session_entry.get().strip()
        if not name or name == "default":
            self._show_error("Enter valid session name (not 'default')")
            return

        new_id = f"qr_{name.lower().replace(' ', '_')}"

        def _work():
            # Connect new session (Node creates fresh)
            result = self.api.connect_account(new_id)
            if result.get("ok"):
                # Add/update account list
                self.accounts[new_id] = AccountInfo(
                    account_id=new_id,
                    phone_number=name,
                    device_name=f"QR Session ({name})",
                    status=ConnectionStatus.CONNECTING,
                )
                ui_dispatch(
                    self,
                    lambda: [
                        self._update_account_selector(),
                        self._load_account(new_id),
                        lambda: self.header_status.configure(
                            text="Scan QR Now",
                            **self._get_badge_colors_from_tone("warning"),
                        ),
                    ],
                )
            else:
                ui_dispatch(
                    self,
                    lambda: self._show_error(
                        f"Failed to create: {result.get('error')}"
                    ),
                )

        start_daemon(_work)
        self.new_session_entry.delete(0, "end")

    def _show_error(self, message: str):
        """Show error state with better visibility"""
        self.qr_image_label.configure(text=f"❌ {message}", image=None)
        badge_colors = self._get_badge_colors_from_tone("danger")
        self.header_status.configure(text="Error", **badge_colors)

    def _update_status_display(self):
        """Update status display"""
        if not self.current_account:
            return

        status = self.current_account.status

        # Map status to badge tone
        tone = "neutral"
        if status == ConnectionStatus.CONNECTED:
            tone = "success"
        elif status == ConnectionStatus.CONNECTING:
            tone = "warning"
        elif status == ConnectionStatus.ERROR:
            tone = "danger"
        elif status == ConnectionStatus.EXPIRED:
            tone = "warning"

        badge_colors = self._get_badge_colors_from_tone(tone)
        self.header_status.configure(text=status.value, **badge_colors)
        self.info_labels["account_status"].configure(text=status.value)

    def _update_session_timer(self):
        """Update session timer"""
        time_remaining = self.session_expires_at - datetime.now()
        minutes = int(time_remaining.total_seconds() // 60)
        seconds = int(time_remaining.total_seconds() % 60)

        if time_remaining.total_seconds() > 0:
            self.session_label.configure(
                text=f"Session expires in {minutes:02d}:{seconds:02d}"
            )
            self.after(1000, self._update_session_timer)
        else:
            self.session_label.configure(text="Session expired")
            self.current_account.status = ConnectionStatus.EXPIRED
            self._update_status_display()

    def _get_badge_colors_from_tone(self, tone: str) -> dict:
        """Map tone to fg/text colors."""
        # Based on LeadWave component conventions
        if tone == "success":
            return {"fg_color": COLORS["success"], "text_color": "white"}
        if tone == "warning":
            return {"fg_color": COLORS["warning"], "text_color": "black"}
        if tone == "danger":
            return {"fg_color": COLORS["danger"], "text_color": "white"}
        if tone == "info":
            return {"fg_color": COLORS["info"], "text_color": "white"}
        # neutral
        return {"fg_color": COLORS["surface_2"], "text_color": COLORS["text_secondary"]}

    def _get_status_color(self, status: ConnectionStatus) -> tuple:
        """Get text color for status"""
        colors = {
            ConnectionStatus.CONNECTED: ("#4CAF50", "#81C784"),
            ConnectionStatus.CONNECTING: ("#FF9800", "#FFB74D"),
            ConnectionStatus.DISCONNECTED: ("#9E9E9E", "#BDBDBD"),
            ConnectionStatus.ERROR: ("#F44336", "#E57373"),
            ConnectionStatus.EXPIRED: ("#FF9800", "#FFB74D"),
        }
        return colors.get(status, ("#999999", "#666666"))

    def _refresh_qr_display(self):
        """Update QR code display"""
        if not self.current_account:
            self.qr_image_label.configure(text="Select Account", image=None)
            return

        def _work():
            img = self._fetch_qr(self.current_account.account_id)

            def _apply():
                if img:
                    size = (260, 260)
                    img_resized = img.resize(size, Image.Resampling.LANCZOS)
                    qr_photo = ctk.CTkImage(
                        light_image=img_resized, dark_image=img_resized, size=size
                    )
                    self.qr_image_label.configure(image=qr_photo, text="")
                    self.qr_image_label.image = qr_photo
                else:
                    self.qr_image_label.configure(text="Generating QR...", image=None)

            ui_dispatch(self, _apply)

        start_daemon(_work)

    def _on_generate_pairing_code(self):
        """Fetch and display a new pairing code."""
        if not self.current_account:
            self.pairing_code_display.configure(text="Select Account")
            return

        # Use manual input if provided, otherwise use account phone
        manual_phone = self.pairing_phone_entry.get().strip()

        # Update UI while working
        self.pairing_code_display.configure(text="Generating...")

        def _work():
            # Pass manual phone if available
            if manual_phone:
                result = self.api.get_pairing_code(
                    self.current_account.account_id, manual_phone
                )
            else:
                result = self._fetch_pairing_code(self.current_account.account_id)

            def _update_ui():
                if result and result.get("ok"):
                    code = result.get("code")
                    self.pairing_code_display.configure(text=code)
                    badge_colors = self._get_badge_colors_from_tone("info")
                    self.header_status.configure(text="Ready to Pair", **badge_colors)
                else:
                    error = result.get("error", "Failed to get code")
                    self.pairing_code_display.configure(text="ERROR")
                    self._show_error(error)

            ui_dispatch(self, _update_ui)

        start_daemon(_work)

    def _on_refresh_qr(self):
        """Refresh QR code"""
        if self.current_account:
            self.current_account.connection_attempts += 1

            # Reset account to generate new QR
            try:
                self.api.reset_account(self.current_account.account_id)
            except Exception as e:
                ui_dispatch(self, lambda: self._show_error(f"Reset failed: {str(e)}"))
                return

            ui_dispatch(self, self._refresh_qr_display)
            self.session_expires_at = datetime.now() + timedelta(minutes=10)

    def _on_save_qr(self):
        """Save QR code as PNG"""
        if not self.current_account:
            return

        img = self._fetch_qr(self.current_account.account_id)
        if img:
            filename = f"qr_{self.current_account.account_id}.png"
            img.save(filename)
            badge_colors = self._get_badge_colors_from_tone("success")
            ui_dispatch(
                self, lambda: self.header_status.configure(text="Saved", **badge_colors)
            )
        else:
            badge_colors = self._get_badge_colors_from_tone("warning")
            ui_dispatch(
                self, lambda: self.header_status.configure(text="No QR", **badge_colors)
            )

    def _on_disconnect(self):
        """Disconnect account"""
        if self.current_account:
            try:
                self.api.logout(self.current_account.account_id)
                self.current_account.status = ConnectionStatus.DISCONNECTED
                self.current_account.connection_attempts = 0
                ui_dispatch(self, self._update_status_display)
            except Exception as e:
                ui_dispatch(
                    self, lambda: self._show_error(f"Disconnect failed: {str(e)}")
                )

    def destroy(self):
        """Cleanup"""
        if self.status_poller_thread:
            # Signal threads to stop (simplified)
            pass
        super().destroy()


# Backward compatibility for main.py
QRLoginTab = Tab
