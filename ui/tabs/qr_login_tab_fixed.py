import customtkinter as ctk
from PIL import Image, ImageDraw, QRCode as QR
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

# Color scheme
class ColorScheme:
    # Light mode
    LIGHT_BG_PRIMARY = "#ffffff"
    LIGHT_BG_SECONDARY = "#f5f5f5"
    LIGHT_BG_TERTIARY = "#fafafa"
    LIGHT_TEXT_PRIMARY = "#1a1a1a"
    LIGHT_TEXT_SECONDARY = "#666666"
    LIGHT_BORDER = "#e0e0e0"
    LIGHT_SUCCESS = "#4CAF50"
    LIGHT_WARNING = "#FFC107"
    LIGHT_ERROR = "#F44336"
    LIGHT_INFO = "#2196F3"
    
    # Dark mode
    DARK_BG_PRIMARY = "#1a1a1a"
    DARK_BG_SECONDARY = "#2a2a2a"
    DARK_BG_TERTIARY = "#242424"
    DARK_TEXT_PRIMARY = "#ffffff"
    DARK_TEXT_SECONDARY = "#cccccc"
    DARK_BORDER = "#404040"
    DARK_SUCCESS = "#81C784"
    DARK_WARNING = "#FFD54F"
    DARK_ERROR = "#EF5350"
    DARK_INFO = "#64B5F6"

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
        
        # Create UI
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        self._create_header(main_container)
        self._create_account_selector(main_container)
        self._create_main_content(main_container)
        self._create_action_buttons(main_container)
        self._create_footer(main_container)
        
        # Apply theme
        apply_leadwave_theme(self)
        
        # Start background tasks
        self._start_background_tasks()
    
    def _start_background_tasks(self):
        """Start daemon threads for loading and polling"""
        self.load_thread = start_daemon(self._load_accounts)
        self.status_poller_thread = start_daemon(self._status_poller)
    
    def _load_accounts(self):
        """Load real accounts from BaileysAPI"""
        try:
            result = self.api.get_accounts()
            if not result.get("ok"):
                ui_dispatch(self, lambda: self._show_error(f"Failed to load accounts: {result.get('error', 'Unknown')}"))
                return
            
            accounts_data = result.get("accounts", [])
            self.accounts = {}
            for acc_data in accounts_data:
                acc_id = acc_data.get("account", "unknown")
                phone = acc_data.get("number", "N/A")
                device = acc_data.get("device_name", f"Device {acc_id}")
                connected = acc_data.get("connected", False)
                status = ConnectionStatus.CONNECTED if connected else ConnectionStatus.DISCONNECTED
                
                self.accounts[acc_id] = AccountInfo(
                    account_id=acc_id,
                    phone_number=phone,
                    device_name=device,
                    status=status
                )
            
            ui_dispatch(self, self._update_account_selector)
            
            if self.accounts:
                first_id = list(self.accounts.keys())[0]
                ui_dispatch(self, lambda: self._load_account(first_id))
            
        except Exception as e:
            ui_dispatch(self, lambda: self._show_error(f"Load accounts error: {str(e)}"))
    
    def _status_poller(self):
        """Poll status every 3 seconds"""
        while True:
            try:
                if self.current_account:
                    result = self.api.get_health(self.current_account.account_id)
                    if result.get("ok"):
                        connected = bool(result.get("connected"))
                        status = ConnectionStatus.CONNECTED if connected else ConnectionStatus.DISCONNECTED
                        
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
        
        for acc_id, acc_info in self.accounts.items():
            self._create_account_button(self.accounts_container, acc_id, acc_info)
    
    def _fetch_qr(self, account_id: str):
        """Fetch real QR from API"""
        try:
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
                    # Raw base64
                    img_data = base64.b64decode(qr_data)
                    img = Image.open(io.BytesIO(img_data))
                    return img
        except Exception:
            pass
        return None
    
    def _create_header(self, parent):
        """Create header section"""
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        title = ctk.CTkLabel(
            header_frame,
            text="WhatsApp Connection",
            font=("Segoe UI", 18, "bold"),
            text_color=("black", "white")
        )
        title.pack(anchor="w", pady=(0, 8))
        
        desc_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        desc_frame.pack(anchor="w", fill="x")
        
        description = ctk.CTkLabel(
            desc_frame,
            text="Scan the QR code with your WhatsApp device to authenticate",
            font=("Segoe UI", 13),
            text_color=("#666666", "#cccccc")
        )
        description.pack(anchor="w", side="left")
        
        # Connection info badge
        self.info_badge = ctk.CTkLabel(
            desc_frame,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color=("#4CAF50", "#81C784")
        )
        self.info_badge.pack(anchor="e", side="right")
    
    def _create_account_selector(self, parent):
        """Create account selector with tabs"""
        selector_frame = ctk.CTkFrame(parent, fg_color="transparent")
        selector_frame.pack(fill="x", pady=(0, 20))
        
        # Horizontal scrollable account selector
        self.accounts_container = ctk.CTkScrollableFrame(
            selector_frame,
            fg_color="transparent",
            orientation="horizontal",
            height=50
        )
        self.accounts_container.pack(fill="x")
    
    def _create_account_button(self, parent, acc_id: str, acc_info: AccountInfo):
        """Create individual account button"""
        status_color = self._get_status_color(acc_info.status)
        
        btn = ctk.CTkButton(
            parent,
            text=f"📱 {acc_info.phone_number}\n{acc_info.status.value}",
            font=("Segoe UI", 11),
            height=45,
            border_width=2,
            border_color=status_color,
            fg_color=("white", "#2a2a2a"),
            hover_color=("#f5f5f5", "#3a3a3a"),
            text_color=("black", "white"),
            command=lambda: self._load_account(acc_id)
        )
        btn.pack(side="left", padx=6)
    
    def _create_main_content(self, parent):
        """Create QR and info section"""
        content_frame = ctk.CTkFrame(parent, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        
        self._create_qr_section(content_frame)
        self._create_info_section(content_frame)
    
    def _create_qr_section(self, parent):
        """Create QR code display"""
        qr_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#2a2a2a"),
            border_width=1,
            border_color=("#e0e0e0", "#404040"),
            corner_radius=12
        )
        qr_frame.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        
        # Top section with title and loading indicator
        top_section = ctk.CTkFrame(qr_frame, fg_color="transparent")
        top_section.pack(fill="x", padx=16, pady=(16, 12))
        
        title = ctk.CTkLabel(
            top_section,
            text="QR Code",
            font=("Segoe UI", 12, "bold"),
            text_color=("#333333", "#cccccc")
        )
        title.pack(side="left")
        
        self.qr_status_label = ctk.CTkLabel(
            top_section,
            text="",
            font=("Segoe UI", 10),
            text_color=("#999999", "#999999")
        )
        self.qr_status_label.pack(side="right")
        
        # QR display area
        self.qr_image_label = ctk.CTkLabel(
            qr_frame,
            text="Generating QR...",
            font=("Segoe UI", 14),
            text_color=("gray", "gray"),
            fg_color=("white", "#1a1a1a"),
            width=200,
            height=200,
            corner_radius=8
        )
        self.qr_image_label.pack(pady=12, padx=16)
        
        # Instructions
        instructions = [
            "1. Open WhatsApp on your phone",
            "2. Tap Menu or Settings",
            "3. Select 'Linked Devices' or 'WhatsApp Web'",
            "4. Point your phone camera at this QR code"
        ]
        
        for instruction in instructions:
            inst_label = ctk.CTkLabel(
                qr_frame,
                text=instruction,
                font=("Segoe UI", 11),
                text_color=("#666666", "#999999")
            )
            inst_label.pack(anchor="w", padx=16, pady=2)
        
        ctk.CTkLabel(qr_frame, text="", fg_color="transparent").pack(pady=(0, 16))
    
    def _create_info_section(self, parent):
        """Create info panels"""
        info_frame = ctk.CTkFrame(parent, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        
        self._create_status_card(info_frame)
        self._create_account_info_card(info_frame)
        self._create_connection_stats_card(info_frame)
        self._create_session_card(info_frame)
    
    def _create_status_card(self, parent):
        """Create connection status card"""
        status_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#2a2a2a"),
            border_width=1,
            border_color=("#e0e0e0", "#404040"),
            corner_radius=8
        )
        status_frame.pack(fill="x", pady=(0, 10))
        
        title = ctk.CTkLabel(
            status_frame,
            text="Connection status",
            font=("Segoe UI", 12, "bold"),
            text_color=("black", "white")
        )
        title.pack(anchor="w", pady=(12, 8), padx=12)
        
        content = ctk.CTkFrame(status_frame, fg_color="transparent")
        content.pack(anchor="w", padx=12, pady=(0, 12))
        
        self.status_indicator = ctk.CTkLabel(
            content,
            text="●",
            font=("Arial", 12),
            text_color=("#999999", "#666666")
        )
        self.status_indicator.pack(side="left", padx=(0, 8))
        
        self.status_text = ctk.CTkLabel(
            content,
            text=ConnectionStatus.DISCONNECTED.value,
            font=("Segoe UI", 13, "bold"),
            text_color=("black", "white")
        )
        self.status_text.pack(side="left")
    
    def _create_account_info_card(self, parent):
        """Create account info card"""
        info_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#2a2a2a"),
            border_width=1,
            border_color=("#e0e0e0", "#404040"),
            corner_radius=8
        )
        info_frame.pack(fill="x", pady=(0, 10))
        
        title = ctk.CTkLabel(
            info_frame,
            text="Account info",
            font=("Segoe UI", 12, "bold"),
            text_color=("black", "white")
        )
        title.pack(anchor="w", pady=(12, 10), padx=12)
        
        info_data = [
            ("Phone:", "account_phone"),
            ("Device:", "account_device"),
            ("Status:", "account_status")
        ]
        
        self.info_labels = {}
        
        for label_text, key in info_data:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            
            label = ctk.CTkLabel(
                row,
                text=label_text,
                font=("Segoe UI", 12),
                text_color=("#666666", "#cccccc")
            )
            label.pack(side="left")
            
            value_label = ctk.CTkLabel(
                row,
                text="—",
                font=("Segoe UI", 12, "bold"),
                text_color=("black", "white")
            )
            value_label.pack(side="right")
            self.info_labels[key] = value_label
        
        ctk.CTkLabel(info_frame, text="", fg_color="transparent").pack(pady=(0, 8))
    
    def _create_connection_stats_card(self, parent):
        """Create connection statistics card"""
        stats_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#2a2a2a"),
            border_width=1,
            border_color=("#e0e0e0", "#404040"),
            corner_radius=8
        )
        stats_frame.pack(fill="x", pady=(0, 10))
        
        title = ctk.CTkLabel(
            stats_frame,
            text="Connection stats",
            font=("Segoe UI", 12, "bold"),
            text_color=("black", "white")
        )
        title.pack(anchor="w", pady=(12, 10), padx=12)
        
        stats_data = [
            ("Attempts:", "stats_attempts"),
            ("Last connected:", "stats_last_connected")
        ]
        
        self.stats_labels = {}
        
        for label_text, key in stats_data:
            row = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            
            label = ctk.CTkLabel(
                row,
                text=label_text,
                font=("Segoe UI", 12),
                text_color=("#666666", "#cccccc")
            )
            label.pack(side="left")
            
            value_label = ctk.CTkLabel(
                row,
                text="—",
                font=("Segoe UI", 12, "bold"),
                text_color=("black", "white")
            )
            value_label.pack(side="right")
            self.stats_labels[key] = value_label
        
        ctk.CTkLabel(stats_frame, text="", fg_color="transparent").pack(pady=(0, 8))
    
    def _create_session_card(self, parent):
        """Create session timer card"""
        session_frame = ctk.CTkFrame(
            parent,
            fg_color=("#E3F2FD", "#1565C0"),
            border_width=1,
            border_color=("#90CAF9", "#0D47A1"),
            corner_radius=8
        )
        session_frame.pack(fill="x")
        
        self.session_label = ctk.CTkLabel(
            session_frame,
            text="ℹ Session expires in 10:00",
            font=("Segoe UI", 12, "bold"),
            text_color=("#1565C0", "#E3F2FD")
        )
        self.session_label.pack(anchor="w", pady=(12, 4), padx=12)
        
        subtitle = ctk.CTkLabel(
            session_frame,
            text="Refresh QR code if scanning fails",
            font=("Segoe UI", 11),
            text_color=("#1976D2", "#BBDEFB")
        )
        subtitle.pack(anchor="w", pady=(0, 12), padx=12)
    
    def _create_action_buttons(self, parent):
        """Create action buttons"""
        button_frame = ctk.CTkFrame(parent, fg_color="transparent")
        button_frame.pack(fill="x", pady=(0, 16))
        
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        
        buttons = [
            ("🔄 Refresh QR", self._on_refresh_qr),
            ("💾 Save QR", self._on_save_qr),
            ("🔗 Disconnect", self._on_disconnect)
        ]
        
        for idx, (text, command) in enumerate(buttons):
            btn = ctk.CTkButton(
                button_frame,
                text=text,
                font=("Segoe UI", 12, "bold"),
                height=36,
                border_width=1,
                border_color=("#d0d0d0", "#505050"),
                fg_color=("white", "#2a2a2a"),
                hover_color=("#f0f0f0", "#3a3a3a"),
                text_color=("black", "white"),
                command=command
            )
            btn.grid(row=0, column=idx, padx=(0, 8) if idx < 2 else (0, 0), sticky="ew")
    
    def _create_footer(self, parent):
        """Create footer"""
        footer_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#2a2a2a"),
            border_width=1,
            border_color=("#e0e0e0", "#404040"),
            corner_radius=8
        )
        footer_frame.pack(fill="x")
        
        footer_text = ctk.CTkLabel(
            footer_frame,
            text="🔒 Security: QR codes expire after 10 minutes. Never share your QR with others. Each code is unique to your session.",
            font=("Segoe UI", 11),
            text_color=("#666666", "#999999"),
            wraplength=700,
            justify="left"
        )
        footer_text.pack(pady=12, padx=12, anchor="w")
    
    def _load_account(self, acc_id: str):
        """Load account and display info"""
        if acc_id not in self.accounts:
            self._show_error("Account not found")
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
        
        # Update info panels
        self.info_labels["account_phone"].configure(text=self.current_account.phone_number)
        self.info_labels["account_device"].configure(text=self.current_account.device_name)
        self.info_labels["account_status"].configure(
            text=self.current_account.status.value,
            text_color=self._get_status_text_color(self.current_account.status)
        )
        
        # Update stats
        self.stats_labels["stats_attempts"].configure(
            text=f"{self.current_account.connection_attempts}/{self.current_account.max_retries}"
        )
        
        if self.current_account.last_connected:
            time_ago = datetime.now() - self.current_account.last_connected
            mins_ago = int(time_ago.total_seconds() // 60)
            self.stats_labels["stats_last_connected"].configure(text=f"{mins_ago} min ago")
        else:
            self.stats_labels["stats_last_connected"].configure(text="Never")
        
        # Reset session timer
        self.session_expires_at = datetime.now() + timedelta(minutes=10)
        self._update_session_timer()
        
        if self.on_account_change:
            self.on_account_change(acc_id)
    
    def _refresh_qr_display(self):
        """Refresh QR display from API"""
        if not self.current_account:
            return
        
        img = self._fetch_qr(self.current_account.account_id)
        if img:
            size = (200, 200)
            img_resized = img.resize(size, Image.Resampling.LANCZOS)
            qr_photo = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=size)
            self.qr_image_label.configure(image=qr_photo, text="")
            self.qr_image_label.image = qr_photo
            self.qr_status_label.configure(text="Ready to scan")
        else:
            self.qr_image_label.configure(text="QR not available", image="")
            self.qr_status_label.configure(text="Generating...")
    
    def _show_error(self, message: str):
        """Show error state"""
        self.qr_image_label.configure(text=message, image="")
        self.status_text.configure(text="Error")
        self.status_indicator.configure(text_color=("#F44336", "#EF5350"))
    
    def _update_status_display(self):
        """Update status display"""
        if not self.current_account:
            return
        
        status = self.current_account.status
        color = self._get_status_color(status)
        
        self.status_indicator.configure(text_color=color)
        self.status_text.configure(text=status.value)
        self.info_badge.configure(text=f"● {status.value}")
        self.info_labels["account_status"].configure(text=status.value)
    
    def _update_session_timer(self):
        """Update session timer"""
        time_remaining = self.session_expires_at - datetime.now()
        minutes = int(time_remaining.total_seconds() // 60)
        seconds = int(time_remaining.total_seconds() % 60)
        
        if time_remaining.total_seconds() > 0:
            self.session_label.configure(
                text=f"ℹ Session expires in {minutes:02d}:{seconds:02d}"
            )
            self.after(1000, self._update_session_timer)
        else:
            self.session_label.configure(text="ℹ Session expired. Click Refresh QR.")
    
    def _get_status_color(self, status: ConnectionStatus) -> tuple:
        """Get color for status"""
        colors = {
            ConnectionStatus.CONNECTED: ("#4CAF50", "#81C784"),
            ConnectionStatus.CONNECTING: ("#FFC107", "#FFD54F"),
            ConnectionStatus.DISCONNECTED: ("#999999", "#666666"),
            ConnectionStatus.ERROR: ("#F44336", "#EF5350"),
            ConnectionStatus.EXPIRED: ("#FF9800", "#FFB74D"),
        }
        return colors.get(status, ("#999999", "#666666"))
    
    def _get_status_text_color(self, status: ConnectionStatus) -> tuple:
        """Get text color for status"""
        colors = {
            ConnectionStatus.CONNECTED: ("#2E7D32", "#81C784"),
            ConnectionStatus.CONNECTING: ("#F57F17", "#FFD54F"),
            ConnectionStatus.DISCONNECTED: ("#666666", "#999999"),
            ConnectionStatus.ERROR: ("#C62828", "#EF5350"),
            ConnectionStatus.EXPIRED: ("#E65100", "#FFB74D"),
        }
        return colors.get(status, ("#666666", "#999999"))
    
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
            ui_dispatch(self, lambda: self.qr_status_label.configure(text=f"Saved as {filename}"))
        else:
            ui_dispatch(self, lambda: self.qr_status_label.configure(text="No QR to save"))
    
    def _on_disconnect(self):
        """Disconnect account"""
        if self.current_account:
            try:
                self.api.logout(self.current_account.account_id)
                self.current_account.status = ConnectionStatus.DISCONNECTED
                self.current_account.connection_attempts = 0
                ui_dispatch(self, self._update_status_display)
            except Exception as e:
                ui_dispatch(self, lambda: self._show_error(f"Disconnect failed: {str(e)}"))
    
    def destroy(self):
        """Cleanup"""
        if self.status_poller_thread:
            # Signal threads to stop (simplified)
            pass
        super().destroy()

# Backward compatibility for main.py
QRLoginTab = Tab

