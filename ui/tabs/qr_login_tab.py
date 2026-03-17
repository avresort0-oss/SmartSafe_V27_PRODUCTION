import base64
import io
import threading
import time

import customtkinter as ctk
from PIL import Image
from ui.theme.icon_registry import load_icon

from core.api.whatsapp_baileys import BaileysAPI
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    body,
    heading,
)
from ui.theme.leadwave_components import (
    CaptionLabel,
    PrimaryButton,
    SectionCard,
    SecondaryButton,
    TabHeader,
    TitleLabel,
)
from ui.utils.threading_helpers import start_daemon, ui_dispatch


class QRLoginTab(ctk.CTkFrame):
    """UI Tab for connecting WhatsApp accounts via QR code."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.api = BaileysAPI()
        self.stop_event = threading.Event()
        self.current_account = ctk.StringVar()
        self._current_account_value = ""
        self.accounts = []
        self.view_state = "idle"  # idle, loading, qr, connected, error

        # Load icons
        try:
            self.success_icon = ctk.CTkImage(load_icon("success", (96, 96)), size=(96, 96))
            self.error_icon = ctk.CTkImage(load_icon("error", (96, 96)), size=(96, 96))
        except Exception:
            self.success_icon = None
            self.error_icon = None

        self._build_ui()

        start_daemon(self.load_accounts)
        start_daemon(self.status_poll_loop)

        self._set_view_state("idle", text="Select an account to begin.")

    def _build_ui(self):
        # Header
        header = TabHeader(
            self,
            title="QR Code Login",
            subtitle="Connect your WhatsApp accounts by scanning the QR code.",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Main content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        # Left panel for controls
        controls_card = SectionCard(content)
        controls_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]))
        controls_frame = controls_card.inner_frame

        TitleLabel(controls_frame, text="Account Control").pack(anchor="w", pady=(0, SPACING["md"]))

        # Account selector
        CaptionLabel(controls_frame, text="Select Account").pack(anchor="w", pady=(SPACING["sm"], SPACING["xxs"]))
        self.account_selector = ctk.CTkOptionMenu(
            controls_frame,
            variable=self.current_account,
            values=["Loading..."],
            command=self.on_account_select,
            font=body(TYPOGRAPHY["body"]),
            height=40,
        )
        self.account_selector.pack(fill="x", pady=(0, SPACING["md"]))

        # Action buttons
        PrimaryButton(
            controls_frame,
            text="Get QR Code",
            command=self.get_qr_code,
            height=40,
        ).pack(fill="x", pady=(0, SPACING["sm"]))

        SecondaryButton(
            controls_frame,
            text="Reset / Logout",
            command=self.reset_account,
            height=40,
        ).pack(fill="x")

        # Right panel for QR code and status
        qr_card = SectionCard(content)
        qr_card.grid(row=0, column=1, sticky="nsew")
        qr_frame = qr_card.inner_frame
        qr_frame.pack_propagate(False)
        qr_frame.grid_columnconfigure(0, weight=1)
        qr_frame.grid_rowconfigure(0, weight=1)

        # --- View States ---
        # Idle State
        self.idle_frame = ctk.CTkFrame(qr_frame, fg_color="transparent")
        self.idle_frame.grid(row=0, column=0, sticky="nsew")
        self.idle_label = CaptionLabel(self.idle_frame, text="Select an account and click 'Get QR Code'.", wraplength=400)
        self.idle_label.place(relx=0.5, rely=0.5, anchor="center")

        # Loading State
        self.loading_frame = ctk.CTkFrame(qr_frame, fg_color="transparent")
        self.loading_frame.grid(row=0, column=0, sticky="nsew")
        loading_content = ctk.CTkFrame(self.loading_frame, fg_color="transparent")
        loading_content.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_progress = ctk.CTkProgressBar(loading_content, mode="indeterminate")
        self.loading_progress.pack()
        self.loading_label = CaptionLabel(loading_content, text="Loading...", wraplength=400)
        self.loading_label.pack(pady=(SPACING["sm"], 0))

        # QR Display State
        self.qr_display_frame = ctk.CTkFrame(qr_frame, fg_color="transparent")
        self.qr_display_frame.grid(row=0, column=0, sticky="nsew")
        qr_content = ctk.CTkFrame(self.qr_display_frame, fg_color="transparent")
        qr_content.place(relx=0.5, rely=0.5, anchor="center")
        self.qr_image_label = ctk.CTkLabel(qr_content, text="")
        self.qr_image_label.pack(pady=SPACING["md"])
        self.qr_status_label = CaptionLabel(qr_content, text="Scan this code with WhatsApp.", wraplength=400)
        self.qr_status_label.pack()

        # Connected State
        self.connected_frame = ctk.CTkFrame(qr_frame, fg_color="transparent")
        self.connected_frame.grid(row=0, column=0, sticky="nsew")
        connected_content = ctk.CTkFrame(self.connected_frame, fg_color="transparent")
        connected_content.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(connected_content, text="", image=self.success_icon).pack()
        TitleLabel(connected_content, text="Account Connected!").pack(pady=(SPACING["sm"], 0))
        self.device_info_label = CaptionLabel(connected_content, text="Device info will appear here.", wraplength=400, justify="left")
        self.device_info_label.pack(pady=(SPACING["xs"], 0))

        # Error State
        self.error_frame = ctk.CTkFrame(qr_frame, fg_color="transparent")
        self.error_frame.grid(row=0, column=0, sticky="nsew")
        error_content = ctk.CTkFrame(self.error_frame, fg_color="transparent")
        error_content.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(error_content, text="", image=self.error_icon).pack()
        self.error_title_label = TitleLabel(error_content, text="An Error Occurred", text_color=COLORS["danger"])
        self.error_title_label.pack(pady=(SPACING["sm"], 0))
        self.error_message_label = CaptionLabel(error_content, text="Error details here.", wraplength=400)
        self.error_message_label.pack(pady=(SPACING["xs"], 0))
        self.retry_button = SecondaryButton(error_content, text="Retry", command=self.get_qr_code)
        self.retry_button.pack(pady=(SPACING["md"], 0))

    def load_accounts(self):
        resp = self.api.get_accounts()
        if resp.get("ok"):
            # API returns: {"accounts": [{"name": "acc1", ...}]}
            self.accounts = [acc.get("name") for acc in resp.get("accounts", []) if acc.get("name")]
            if self.accounts:
                def _update_ui():
                    self.account_selector.configure(values=self.accounts)
                    self.current_account.set(self.accounts[0])
                    self._current_account_value = self.accounts[0]
                    self.on_account_select(self.accounts[0])
                ui_dispatch(self, _update_ui)
            else:
                # No existing accounts - use default
                def _use_default():
                    self.account_selector.configure(values=["default"])
                    self.current_account.set("default")
                    self._current_account_value = "default"
                    self._set_view_state("idle", text="No accounts found. Using 'default' account.")
                    # Auto-fetch QR for default account
                    self.on_account_select("default")
                ui_dispatch(self, _use_default)
        else:
            # Server error - use default account
            def _use_default_error():
                self.account_selector.configure(values=["default"])
                self.current_account.set("default")
                self._current_account_value = "default"
                self._set_view_state("idle", text="Using default account.")
                # Auto-fetch QR for default account
                self.on_account_select("default")
            ui_dispatch(self, _use_default_error)

    def on_account_select(self, account: str):
        self._current_account_value = account
        self.current_account.set(account)
        self.check_connection_status(account)
        # Automatically fetch QR code when account is selected
        self.get_qr_code()

    def get_qr_code(self):
        account = self.current_account.get()
        if not account:
            self._set_view_state("error", title="No Account", text="Please select an account first.")
            return

        self._set_view_state("loading", text=f"Initializing session for {account}...")
        # First create/connect the session, then get the QR code
        start_daemon(self._connect_and_get_qr_worker, account)

    def _set_view_state(self, state: str, **kwargs):
        """Update the UI to show a specific state."""
        self.view_state = state
        
        # Hide all frames
        for frame in [self.idle_frame, self.loading_frame, self.qr_display_frame, self.connected_frame, self.error_frame]:
            frame.grid_remove()

        if state == "idle":
            self.idle_label.configure(text=kwargs.get("text", "Select an account."))
            self.idle_frame.grid()
        elif state == "loading":
            self.loading_label.configure(text=kwargs.get("text", "Loading..."))
            self.loading_progress.start()
            self.loading_frame.grid()
        elif state == "qr":
            self.qr_image_label.configure(image=kwargs.get("image"))
            self.qr_status_label.configure(text=kwargs.get("text", "Scan QR code."))
            self.qr_display_frame.grid()
        elif state == "connected":
            self.device_info_label.configure(text=kwargs.get("text", "Connected successfully."))
            self.connected_frame.grid()
        elif state == "error":
            self.error_title_label.configure(text=kwargs.get("title", "Error"))
            self.error_message_label.configure(text=kwargs.get("text", "An unknown error occurred."))
            self.error_frame.grid()

    def _connect_and_get_qr_worker(self, account: str):
        """Connect to create session, then fetch QR code with retry mechanism."""
        
        # Step 1: Connect/create session with extended timeout (90 seconds)
        connect_resp = self.api.connect_account(account, timeout=90.0)

        if not connect_resp.get("ok"):
            error_msg = connect_resp.get('error', 'Unknown error')
            code = connect_resp.get('code', '')
            
            # Provide helpful error messages based on error type
            if code == 'TIMEOUT' or 'timeout' in error_msg.lower():
                friendly_msg = (
                    f"⏱️ Connection timeout for '{account}'.\n\n"
                    "Trying alternative method...\n"
                    "Please wait while we fetch the QR code."
                )
                ui_dispatch(self, lambda: self._set_view_state("loading", text=friendly_msg))
                
                # Fallback: Try direct QR fetch after short delay
                time.sleep(2)
                self._retry_qr_fetch(account)
                return
                
            elif code == 'CONNECTION_ERROR':
                friendly_msg = (
                    f"❌ Cannot connect to WhatsApp server.\n\n"
                    "Please ensure the Node.js server is running:\n"
                    "Run: npm start (in server directory)"
                )
            else:
                friendly_msg = f"❌ Failed to create session:\n{error_msg}\n\nTry clicking 'Reset / Logout' first."
            
            ui_dispatch(self, lambda: self._set_view_state("error", title="Connection Failed", text=friendly_msg))
            return

        # If already connected, show success
        if connect_resp.get("connected"):
            self.check_connection_status(account)
            return

        # If the connect response contains the QR, render it directly
        qr_data_url = connect_resp.get("qr")
        if qr_data_url:
            self._render_qr_code(account, qr_data_url)
            return

        # Fallback: Poll for QR code with retry
        self._retry_qr_fetch(account)

    def _render_qr_code(self, account: str, qr_data_url: str):
        """Helper to render QR code image."""
        try:
            _header, encoded = qr_data_url.split(",", 1)
            image_data = base64.b64decode(encoded)
            pil_image = Image.open(io.BytesIO(image_data)).resize((280, 280), Image.Resampling.LANCZOS)
            ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(280, 280))
            
            text = f"📱 Scan QR code with WhatsApp\nAccount: {account}"
            ui_dispatch(self, lambda: self._set_view_state("qr", image=ctk_image, text=text))
        except Exception as e:
            ui_dispatch(self, lambda: self._set_view_state("error", title="QR Render Failed", text=f"Failed to display QR code: {e}"))

    def _retry_qr_fetch(self, account: str):
        """Retry fetching QR code multiple times."""
        ui_dispatch(self, lambda: self._set_view_state("loading", text="⏳ Fetching QR code...\nPlease wait..."))
        
        # Try fetching QR code multiple times with delays
        max_retries = 5
        for attempt in range(max_retries):
            time.sleep(2)  # Wait 2 seconds between attempts
            
            qr_resp = self.api.get_qr(account)
            
            # Check if connected
            if qr_resp.get("connected"):
                self.check_connection_status(account)
                return
            
            # Check if QR is available
            qr_data = qr_resp.get("qr")
            if qr_data:
                self._render_qr_code(account, qr_data)
                return
            
            # Update attempt status
            remaining = max_retries - attempt - 1
            if remaining > 0:
                text = f"⏳ Waiting for QR code...\nRetrying... ({remaining} attempts left)"
                ui_dispatch(self, lambda: self._set_view_state("loading", text=text))
        
        # All retries exhausted
        error_text = (
            f"Could not fetch QR code for '{account}'.\n\n"
            "Please try:\n"
            "1. Click 'Reset / Logout' first\n"
            "2. Then click 'Get QR Code' again\n"
            "3. Ensure Node.js server is running"
        )
        ui_dispatch(self, lambda: self._set_view_state("error", title="QR Fetch Failed", text=error_text))

    def reset_account(self):
        account = self.current_account.get()
        if not account: return
        self._set_view_state("loading", text=f"Resetting account {account}...")
        start_daemon(self._reset_worker, account)

    def _reset_worker(self, account: str):
        resp = self.api.reset_account(account)
        def _update_ui():
            if resp.get("ok"):
                self._set_view_state("idle", text=f"✅ Account '{account}' has been reset.\nClick 'Get QR Code' to reconnect.")
            else:
                self._set_view_state("error", title="Reset Failed", text=f"Failed to reset account: {resp.get('error')}")
        ui_dispatch(self, _update_ui)

    def status_poll_loop(self):
        while not self.stop_event.is_set():
            account = self._current_account_value
            if account:
                self.check_connection_status(account, silent=True)
            self.stop_event.wait(5)

    def check_connection_status(self, account: str, silent: bool = False):
        start_daemon(self._check_status_worker, account, silent)

    def _check_status_worker(self, account: str, silent: bool):
        resp = self.api.get_status(account=account)
        def _update_ui():
            if self.current_account.get() != account or self.view_state == "loading":
                return
                
            if resp.get("ok") and resp.get("connected"):
                dev = resp.get("device", {})
                info_text = (
                    f"Account: {resp.get('account', account)}\n"
                    f"Number: {dev.get('number', '-')}\n"
                    f"Device: {dev.get('model', '-')}\n"
                    f"Platform: {dev.get('platform', '-')}"
                )
                self._set_view_state("connected", text=info_text)
            elif not silent:
                status_text = f"Status for '{account}': {resp.get('status', 'Unknown')}"
                self._set_view_state("idle", text=status_text)
        ui_dispatch(self, _update_ui)

    def destroy(self):
        self.stop_event.set()
        super().destroy()
