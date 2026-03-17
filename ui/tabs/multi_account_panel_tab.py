import base64
import io
import threading
import time
import os
import json
from datetime import datetime
from typing import Any
from tkinter import messagebox

import customtkinter as ctk
import qrcode
from PIL import Image

from core.api.whatsapp_baileys import BaileysAPI
from core.config import SETTINGS
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    RADIUS,
    TabHeader,
    StatusBadge,
    heading,
    body,
    SectionCard,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    StyledTextbox,
)
from ui.theme.leadwave_components import apply_leadwave_theme


class Tab(ctk.CTkFrame):
    """SmartSafe V27 - Multi-account control center."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.api = BaileysAPI()
        self.auto_refresh = True
        # Slightly slower polling to reduce background load on the server/UI.
        self.refresh_interval = 6
        self.stop_event = threading.Event()

        self.accounts_file = "accounts_config.json"
        self.accounts_data = self._load_accounts_from_file()
        self.accounts = [acc.get("name") for acc in self.accounts_data] or ["acc1"]
        self.selected_account = self.accounts[0] if self.accounts else "acc1"

        self._build_ui()
        # Apply LeadWave theming to harmonize this tab with the new premium UI.
        apply_leadwave_theme(self)
        start_daemon(self._sync_accounts_from_api)
        self.refresh_now(silent=False)
        start_daemon(self._auto_loop)

    def _build_ui(self):
        header = TabHeader(
            self,
            title="Multi-Account Control Center",
            subtitle="Manage sessions, QR logins, and quick tools",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Status Badge
        badge_colors = self._get_badge_colors_from_tone("success")
        self.header_status_badge = StatusBadge(
            header.actions, text="ACTIVE", **badge_colors
        )
        self.header_status_badge.pack(side="right")

        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=3)  # Right panel wider
        main.grid_rowconfigure(0, weight=1)

        # --- Left Column (Account List) ---
        left_card = SectionCard(main)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))

        ctk.CTkLabel(
            left_card.inner_frame,
            text="Accounts",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        self.account_list_frame = ctk.CTkScrollableFrame(
            left_card.inner_frame, fg_color=COLORS["app_bg"], corner_radius=RADIUS["md"]
        )
        self.account_list_frame.pack(fill="both", expand=True)

        PrimaryButton(
            left_card.inner_frame,
            text="Add New Account",
            command=self.add_account_dialog,
        ).pack(fill="x", pady=(SPACING["xs"], 0))

        # --- Right Column (Details) ---
        right_col = ctk.CTkFrame(main, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))

        # Top Actions Bar
        action_card = SectionCard(right_col)
        action_card.pack(fill="x", pady=(0, SPACING["sm"]))

        action_grid = ctk.CTkFrame(action_card.inner_frame, fg_color="transparent")
        action_grid.pack(fill="x")

        self.acc_title = ctk.CTkLabel(
            action_grid,
            text="Selected: acc1",
            font=heading(TYPOGRAPHY["h2"], "bold"),
            text_color=COLORS["brand"],
        )
        self.acc_title.pack(side="left")

        SecondaryButton(
            action_grid,
            text="Logout",
            command=self.logout_device,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color=COLORS["text_inverse"],
            width=80,
        ).pack(side="right", padx=(4, 0))
        self.auto_btn = SecondaryButton(
            action_grid, text="Auto: ON", command=self.toggle_auto, width=80
        )
        self.auto_btn.pack(side="right", padx=(4, 0))
        SecondaryButton(
            action_grid,
            text="Refresh",
            command=lambda: self.refresh_now(silent=False),
            width=80,
        ).pack(side="right")

        # Status & QR Card
        status_card = SectionCard(right_col)
        status_card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            status_card.inner_frame,
            text="Connection Status",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        self.connection_status_label = ctk.CTkLabel(
            status_card.inner_frame,
            text="Status: idle",
            font=heading(TYPOGRAPHY["h2"], "bold"),
            text_color=COLORS["warning"],
        )
        self.connection_status_label.pack(pady=(0, SPACING["sm"]))

        self.device_label = ctk.CTkLabel(
            status_card.inner_frame,
            text="Account: -\nNumber: -\nDevice: -\nPlatform: -\nLogin: -\nLast Sync: -",
            justify="left",
            font=body(TYPOGRAPHY["mono"]),
            text_color=COLORS["text_secondary"],
        )
        self.device_label.pack(anchor="w", padx=SPACING["md"], pady=SPACING["xs"])

        self.qr_label = ctk.CTkLabel(
            status_card.inner_frame,
            text="QR will show here",
            text_color=COLORS["text_muted"],
        )
        self.qr_label.pack(pady=SPACING["sm"], expand=True)

        # Quick Actions Card
        quick_card = SectionCard(right_col)
        quick_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(
            quick_card.inner_frame,
            text="Quick Tools",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        # Test Send
        ctk.CTkLabel(
            quick_card.inner_frame,
            text="Test Message",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.send_number_entry = StyledInput(
            quick_card.inner_frame, placeholder_text="Phone (with country code)"
        )
        self.send_number_entry.pack(fill="x", pady=(0, SPACING["xs"]))
        self.send_message_entry = StyledInput(
            quick_card.inner_frame, placeholder_text="Message"
        )
        self.send_message_entry.pack(fill="x", pady=(0, SPACING["xs"]))

        send_row = ctk.CTkFrame(quick_card.inner_frame, fg_color="transparent")
        send_row.pack(fill="x", pady=(0, SPACING["sm"]))
        SecondaryButton(send_row, text="Send Test", command=self.quick_send).pack(
            side="left"
        )
        self.send_status = ctk.CTkLabel(
            send_row,
            text="",
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_muted"],
        )
        self.send_status.pack(side="left", padx=SPACING["xs"])

        # Profile Check
        ctk.CTkLabel(
            quick_card.inner_frame,
            text="Quick Profile Check",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.profile_number_entry = StyledInput(
            quick_card.inner_frame, placeholder_text="Phone (with country code)"
        )
        self.profile_number_entry.pack(fill="x", pady=(0, SPACING["xs"]))

        check_row = ctk.CTkFrame(quick_card.inner_frame, fg_color="transparent")
        check_row.pack(fill="x")
        SecondaryButton(
            check_row, text="Check Profile", command=self.quick_profile_check
        ).pack(side="left")
        self.profile_status = ctk.CTkLabel(
            check_row,
            text="",
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_muted"],
        )
        self.profile_status.pack(side="left", padx=SPACING["xs"])

        # ========== Smart Anti-Ban Controls ==========
        ctk.CTkLabel(
            quick_card.inner_frame,
            text="🛡️ Smart Anti-Ban",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(SPACING["md"], SPACING["xxs"]))

        # Read Receipts Toggle
        receipt_frame = ctk.CTkFrame(quick_card.inner_frame, fg_color="transparent")
        receipt_frame.pack(fill="x", pady=(0, SPACING["xs"]))
        ctk.CTkLabel(
            receipt_frame, text="Read Receipts:", font=body(TYPOGRAPHY["caption"])
        ).pack(side="left")
        self.read_receipts_var = ctk.BooleanVar(
            value=SETTINGS.read_receipt_mode != "off"
        )
        ctk.CTkSwitch(
            receipt_frame, text="", variable=self.read_receipts_var, width=50
        ).pack(side="right")

        # Backup Button
        backup_btn = SecondaryButton(
            quick_card.inner_frame,
            text="💾 Backup Session",
            command=self.backup_session,
        )
        backup_btn.pack(fill="x", pady=(0, SPACING["sm"]))

        # Proxy Status (dynamic)
        self.proxy_status_label = ctk.CTkLabel(
            quick_card.inner_frame,
            text="Proxy: Loading...",
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_muted"],
        )
        self.proxy_status_label.pack(anchor="w")

        # Monitor Card
        monitor_card = SectionCard(right_col)
        monitor_card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            monitor_card.inner_frame,
            text="SmartSafe Anti-Ban Status",
            font=heading(TYPOGRAPHY["h3"], "bold"),
            text_color=COLORS["brand"],
        ).pack(anchor="w", pady=(0, SPACING["xs"]))

        self.monitor_label = StyledTextbox(monitor_card.inner_frame)
        self.monitor_label.pack(fill="both", expand=True)
        self.monitor_label.configure(state="disabled")

    def _render_account_list(self):
        """
        Render the list of accounts on the left panel in small batches so
        large account lists don't freeze the UI.
        """
        # Bump a render token so older in‑flight renders stop early
        current_token = getattr(self, "_account_list_render_token", 0) + 1
        self._account_list_render_token = current_token

        # Clear existing widgets once per render
        for widget in self.account_list_frame.winfo_children():
            widget.destroy()

        accounts_snapshot = list(self.accounts)
        batch_size = 10

        def _render_batch(start_index: int = 0):
            # If a newer render was started, abort this one
            if current_token != getattr(self, "_account_list_render_token", 0):
                return

            end_index = min(start_index + batch_size, len(accounts_snapshot))
            for acc in accounts_snapshot[start_index:end_index]:
                is_selected = acc == self.selected_account

                acc_data = next(
                    (item for item in self.accounts_data if item.get("name") == acc), {}
                )
                phone = acc_data.get("phone", "N/A")
                status = acc_data.get("status", "offline")

                btn_color = COLORS["brand"] if is_selected else COLORS["surface_2"]
                text_color = "white" if is_selected else COLORS["text_primary"]
                subtext_color = "white" if is_selected else COLORS["text_muted"]
                hover_color = (
                    COLORS["brand_hover"] if is_selected else COLORS["surface_3"]
                )

                card = ctk.CTkFrame(
                    self.account_list_frame,
                    fg_color=btn_color,
                    corner_radius=RADIUS["md"],
                )
                card.pack(fill="x", pady=SPACING["xxs"], padx=SPACING["xxs"])

                def on_enter(e, c=card, h=hover_color):
                    c.configure(fg_color=h)

                def on_leave(e, c=card, b=btn_color):
                    c.configure(fg_color=b)

                def on_click(e, a=acc):
                    self.select_account(a)

                card.bind("<Enter>", on_enter)
                card.bind("<Leave>", on_leave)
                card.bind("<Button-1>", on_click)

                icon_frame = ctk.CTkFrame(card, fg_color="transparent")
                icon_frame.pack(
                    side="left", padx=(SPACING["sm"], SPACING["xs"]), pady=SPACING["xs"]
                )
                icon_frame.bind("<Button-1>", on_click)

                icon = ctk.CTkLabel(
                    icon_frame,
                    text="👤",
                    font=heading(TYPOGRAPHY["h2"]),
                    text_color=text_color,
                )
                icon.pack(side="left")
                icon.bind("<Button-1>", on_click)

                dot_color = (
                    COLORS["success"] if status == "active" else COLORS["danger"]
                )
                status_dot = ctk.CTkLabel(
                    icon_frame,
                    text="●",
                    font=body(TYPOGRAPHY["caption"], "bold"),
                    text_color=dot_color,
                )
                status_dot.place(relx=0.7, rely=0.7)
                status_dot.bind("<Button-1>", on_click)

                info_frame = ctk.CTkFrame(card, fg_color="transparent")
                info_frame.pack(
                    side="left", fill="both", expand=True, pady=SPACING["xs"]
                )
                info_frame.bind("<Button-1>", on_click)

                name_lbl = ctk.CTkLabel(
                    info_frame,
                    text=acc,
                    font=body(TYPOGRAPHY["body"], "bold"),
                    text_color=text_color,
                    anchor="w",
                )
                name_lbl.pack(fill="x")
                name_lbl.bind("<Button-1>", on_click)

                phone_lbl = ctk.CTkLabel(
                    info_frame,
                    text=phone,
                    font=body(TYPOGRAPHY["caption"]),
                    text_color=subtext_color,
                    anchor="w",
                )
                phone_lbl.pack(fill="x")
                phone_lbl.bind("<Button-1>", on_click)

                del_btn = ctk.CTkButton(
                    card,
                    text="DEL",
                    width=36,
                    height=36,
                    fg_color=COLORS["surface_1"],
                    text_color=COLORS["danger"],
                    hover_color=COLORS["surface_3"],
                    command=lambda a=acc: self.delete_account(a),
                )
                del_btn.pack(side="right", padx=SPACING["xs"])

            if end_index < len(accounts_snapshot):
                # Schedule the next small batch so the event loop can breathe
                self.after(1, lambda: _render_batch(end_index))

        _render_batch(0)

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

    def _load_accounts_from_file(self):
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_accounts_to_file(self):
        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                json.dump(self.accounts_data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save accounts file: {e}")

    def _sync_accounts_from_api(self):
        """Merges accounts from the API with the local list without overwriting."""
        result = self.api.get_accounts()
        if not result.get("ok"):
            return

        api_accounts = [
            item.get("account")
            for item in result.get("accounts", [])
            if item.get("account")
        ]
        if not api_accounts:
            return

        added = False
        current_names = {acc.get("name") for acc in self.accounts_data}
        for acc_name in api_accounts:
            if acc_name not in current_names:
                self.accounts_data.append(
                    {"name": acc_name, "status": "offline", "phone": "N/A"}
                )
                self.accounts.append(acc_name)
                added = True

        if added:
            self._save_accounts_to_file()

        def _apply():
            self._render_account_list()

        ui_dispatch(self, _apply)

    def delete_account(self, account_name):
        """Delete an account from the list"""
        if not messagebox.askyesno(
            "Confirm Delete", f"Are you sure you want to delete '{account_name}'?"
        ):
            return

        # Remove from memory
        if account_name in self.accounts:
            self.accounts.remove(account_name)

        self.accounts_data = [
            acc for acc in self.accounts_data if acc.get("name") != account_name
        ]

        # Save to disk
        self._save_accounts_to_file()

        # Handle selection if we deleted the current account
        if self.selected_account == account_name:
            self.selected_account = self.accounts[0] if self.accounts else None
            if self.selected_account:
                self.select_account(self.selected_account)
            else:
                # Clear UI if no accounts left
                self.acc_title.configure(text="No Accounts")
                self.device_label.configure(text="No account selected")
                self.qr_label.configure(image=None, text="")
                self.connection_status_label.configure(
                    text="---", text_color=COLORS["text_muted"]
                )

        self._render_account_list()

    def add_log(self, message, level="info"):
        """Add log entry to monitor"""
        if not hasattr(self, "monitor_label"):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"[{timestamp}] {message}\n"
        self.monitor_label.configure(state="normal")
        self.monitor_label.insert("end", text)
        self.monitor_label.see("end")
        self.monitor_label.configure(state="disabled")

    def add_account_dialog(self):
        """Show dialog to add a new account, similar to Balancer tab."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add New Account")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        apply_leadwave_theme(dialog)

        content = ctk.CTkFrame(dialog, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            content, text="Add New Account", font=heading(TYPOGRAPHY["h2"], "bold")
        ).pack(pady=(0, 20))

        ctk.CTkLabel(
            content,
            text="Account Name (e.g., acc3, marketing_acc)",
            font=body(TYPOGRAPHY["body"], "bold"),
        ).pack(anchor="w")
        name_entry = StyledInput(content, placeholder_text="acc3")
        name_entry.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(
            content,
            text="Phone Number (Optional)",
            font=body(TYPOGRAPHY["body"], "bold"),
        ).pack(anchor="w")
        phone_entry = StyledInput(content, placeholder_text="+880...")
        phone_entry.pack(fill="x", pady=(4, 12))

        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(20, 0))

        def save_account():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning(
                    "Warning", "Account Name is required.", parent=dialog
                )
                return

            if any(acc.get("name") == name for acc in self.accounts_data):
                messagebox.showerror(
                    "Error", f"Account '{name}' already exists.", parent=dialog
                )
                return

            new_account = {
                "name": name,
                "phone": phone_entry.get().strip() or "N/A",
                "status": "offline",
            }
            self.accounts_data.append(new_account)
            self.accounts.append(name)
            self._save_accounts_to_file()
            self._render_account_list()
            self.select_account(name)
            self.add_log(f"Added new account: {name}")
            dialog.destroy()

        PrimaryButton(btn_frame, text="Add Account", command=save_account).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        SecondaryButton(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", fill="x", expand=True, padx=(5, 0)
        )

    def select_account(self, account):
        if not account:
            return
        self.selected_account = account
        self.api.set_account(account)
        self._render_account_list()
        self.acc_title.configure(text=f"Selected: {account}")
        self.refresh_now(silent=False)

    def toggle_auto(self):
        self.auto_refresh = not self.auto_refresh
        ui_dispatch(
            self,
            lambda: self.auto_btn.configure(
                text="Auto: ON" if self.auto_refresh else "Auto: OFF"
            ),
        )

    def activate_account(self):
        # Deprecated, handled by select_account
        pass

    def logout_device(self):
        account = self.selected_account
        result = self.api.logout(account=account)
        if not result.get("ok"):
            ui_dispatch(
                self,
                lambda: self.connection_status_label.configure(
                    text=f"Logout error: {result.get('error')}",
                    text_color=COLORS["danger"],
                ),
            )
            return
        ui_dispatch(
            self,
            lambda: self.connection_status_label.configure(
                text="Logged out", text_color=COLORS["warning"]
            ),
        )
        self.refresh_now(silent=True)

    def refresh_now(self, silent: bool = True):
        start_daemon(self._load_status_qr, silent)

    def _auto_loop(self):
        while not self.stop_event.is_set():
            if self.auto_refresh:
                self._load_status_qr(silent=True)
                self._update_monitor()
            self.stop_event.wait(self.refresh_interval)

    def _load_status_qr(self, silent: bool = True):
        account = self.selected_account

        status = self.api.get_health(account=account)

        if not status.get("ok"):
            if not silent:
                ui_dispatch(
                    self,
                    lambda: self.connection_status_label.configure(
                        text=f"Error: {status.get('error')}",
                        text_color=COLORS["danger"],
                    ),
                )
            return

        is_connected = (
            status.get("connected")
            or str(status.get("status", "")).lower() == "connected"
        )
        if not is_connected:
            connect_result = self.api.connect_account(account)
            if not connect_result.get("ok"):
                if not silent:
                    ui_dispatch(
                        self,
                        lambda: self.connection_status_label.configure(
                            text=f"Connection error: {connect_result.get('error')}",
                            text_color=COLORS["danger"],
                        ),
                    )
                return
            status = self.api.get_health(account=account)

        qr_data = self.api.get_qr(account=account)

        if not status.get("ok"):
            if not silent:
                ui_dispatch(
                    self,
                    lambda: self.connection_status_label.configure(
                        text=f"Error: {status.get('error')}",
                        text_color=COLORS["danger"],
                    ),
                )
            return

        current_acc = status.get("account") or status.get("current_account") or account
        dev = status.get("device") or {}

        # Update status in local data for the list dot
        is_connected = (
            qr_data.get("connected")
            or str(qr_data.get("status", "")).lower() == "connected"
        )
        new_status = "active" if is_connected else "offline"
        for item in self.accounts_data:
            if item.get("name") == account:
                item["status"] = new_status
                break

        # Update local data if phone number is found
        number = dev.get("number")
        if number:
            updated = False
            for item in self.accounts_data:
                if item.get("name") == account:
                    if item.get("phone") != number:
                        item["phone"] = number
                        updated = True
                    break

        # Save and re-render list to show updated status dot
        self._save_accounts_to_file()
        ui_dispatch(self, self._render_account_list)

        def _update_device():
            self.device_label.configure(
                text=(
                    f"Account: {current_acc}\n"
                    f"Number: {dev.get('number', '-')}\n"
                    f"Device: {dev.get('model', '-')}\n"
                    f"Platform: {dev.get('platform', '-')}\n"
                    f"Login: {dev.get('login_time', '-')}\n"
                    f"Last Sync: {dev.get('last_sync', '-')}"
                )
            )

        ui_dispatch(self, _update_device)

        if (
            qr_data.get("connected")
            or str(qr_data.get("status", "")).lower() == "connected"
        ):
            ui_dispatch(
                self,
                lambda: self.connection_status_label.configure(
                    text="CONNECTED", text_color=COLORS["success"]
                ),
            )
            ui_dispatch(
                self,
                lambda: self.qr_label.configure(
                    text="WhatsApp is connected", image=None
                ),
            )
            return

        qr_value = qr_data.get("qr")
        if not qr_value:
            ui_dispatch(
                self,
                lambda: self.connection_status_label.configure(
                    text="Waiting for QR...", text_color=COLORS["warning"]
                ),
            )
            ui_dispatch(
                self, lambda: self.qr_label.configure(text="No QR yet", image=None)
            )
            return

        self._render_qr(qr_value)

    def _render_qr(self, qr_value: str):
        try:
            if qr_value.startswith("data:image") and "," in qr_value:
                _, encoded = qr_value.split(",", 1)
                img = Image.open(io.BytesIO(base64.b64decode(encoded)))
            else:
                img = qrcode.make(qr_value)

            img = img.resize((280, 280))  # type: ignore[attr-defined]
            qr_img = ctk.CTkImage(light_image=img, dark_image=img, size=(280, 280))

            def _apply():
                self.qr_label.configure(image=qr_img, text="")
                self.qr_label.image = qr_img  # type: ignore[attr-defined]
                self.connection_status_label.configure(
                    text="SCAN QR TO LOGIN", text_color=COLORS["warning"]
                )

            ui_dispatch(self, _apply)
        except Exception as exc:
            ui_dispatch(
                self,
                lambda: self.connection_status_label.configure(
                    text=f"QR render error: {exc}", text_color=COLORS["danger"]
                ),
            )

    def _update_monitor(self):
        result = self.api.get_stats()
        if not result.get("ok"):
            return

        current = result.get("current_account")
        stats = result.get("stats", {}) or {}

        total_accounts = len(stats)
        active_accounts = 0
        total_sent = 0
        total_errors = 0

        lines = []
        for account, row in stats.items():
            is_connected = bool(row.get("connected"))
            if is_connected:
                active_accounts += 1
            sent = int(row.get("messages_sent", 0) or 0)
            errors = int(row.get("errors", 0) or 0)
            total_sent += sent
            total_errors += errors

            active_flag = "(active)" if account == current else ""
            lines.append(
                f"{account} {active_flag} - status={row.get('status')} sent={sent} "
                f"checks={row.get('profile_checks', 0)} errors={errors} "
                f"last_error={row.get('last_error') or '-'}"
            )

        # Queue length and engine load are optional but useful when exposed by the API.
        queue_len = int(result.get("queue_length", 0) or result.get("queue", 0) or 0)
        ops = max(1, total_errors + total_sent)
        error_rate = (total_errors / ops) * 100

        header = (
            "System Status Board\n"
            f"Accounts: {active_accounts}/{total_accounts} | "
            f"Sent: {total_sent} | Errors: {total_errors} ({error_rate:.1f}% error) | "
            f"Queue: {queue_len}\n"
            "—" * 72
        )

        text = header + "\n" + "\n".join(lines)

        def _apply():
            self.monitor_label.configure(state="normal")
            self.monitor_label.delete("1.0", "end")
            self.monitor_label.insert("1.0", text)
            self.monitor_label.configure(state="disabled")

        ui_dispatch(self, _apply)

    def quick_send(self):
        number = (self.send_number_entry.get() or "").strip()
        message = (self.send_message_entry.get() or "").strip()
        account = self.selected_account

        if not number or not message:
            ui_dispatch(
                self,
                lambda: self.send_status.configure(
                    text="Number + Message required", text_color=COLORS["danger"]
                ),
            )
            return

        def _work():
            resp = self.api.send_message(number, message, account=account)
            if not resp.get("ok"):
                ui_dispatch(
                    self,
                    lambda: self.send_status.configure(
                        text=f"Send failed: {resp.get('error')}",
                        text_color=COLORS["danger"],
                    ),
                )
                return
            ui_dispatch(
                self,
                lambda: self.send_status.configure(
                    text=f"Sent via {resp.get('account', account)}",
                    text_color=COLORS["success"],
                ),
            )

        start_daemon(_work)

    def quick_profile_check(self):
        number = (self.profile_number_entry.get() or "").strip()
        account = self.selected_account

        if not number:
            ui_dispatch(
                self,
                lambda: self.profile_status.configure(
                    text="Number required", text_color=COLORS["danger"]
                ),
            )
            return

        def _work():
            resp = self.api.profile_check(number, account=account)
            if not resp.get("ok"):
                ui_dispatch(
                    self,
                    lambda: self.profile_status.configure(
                        text=f"Check failed: {resp.get('error')}",
                        text_color=COLORS["danger"],
                    ),
                )
                return

            exists = bool(resp.get("exists"))
            message = (
                f"Exists (via {resp.get('account', account)})"
                if exists
                else f"Not on WhatsApp"
            )
            color = COLORS["success"] if exists else COLORS["warning"]
            ui_dispatch(
                self,
                lambda: self.profile_status.configure(text=message, text_color=color),
            )

        start_daemon(_work)

    def backup_session(self):
        """Backup current account session to Google Drive"""
        account = self.selected_account
        if not account:
            messagebox.showwarning("Warning", "Select an account first")
            return

        def _work():
            result = self.api.session_backup(account)
            if result.get("ok"):
                url = result.get("driveUrl", "Backup complete")
                self.add_log(f"✅ Session backed up: {url}")
            else:
                self.add_log(f"❌ Backup failed: {result.get('error')}", "error")

        start_daemon(_work)
        self.add_log(f"🔄 Backing up session for {account}...")

    def update_anti_ban_status(self):
        """Update proxy/read receipt status display"""
        try:
            from core.engine.proxy_rotator import get_proxy_rotator

            rotator = get_proxy_rotator()
            stats = rotator.get_stats(self.selected_account)

            proxy_text = (
                f"Proxy: {stats['healthy_proxies']}/{stats['total_proxies']} healthy"
            )
            color = (
                COLORS["success"] if stats["healthy_proxies"] > 0 else COLORS["warning"]
            )

            self.proxy_status_label.configure(text=proxy_text, text_color=color)

            receipt_text = (
                f"Read Receipts: {'ON' if self.read_receipts_var.get() else 'OFF'}"
            )
            self.add_log(receipt_text)
        except Exception as e:
            self.proxy_status_label.configure(
                text=f"Proxy: Error ({e})", text_color=COLORS["danger"]
            )

    def destroy(self):
        if hasattr(self, "stop_event"):
            self.stop_event.set()
        try:
            self.api.close()
        except Exception:
            pass
        super().destroy()


# Alias for backward compatibility with main.py
MultiAccountPanelTab = Tab


# Alias for backward compatibility with main.py
MultiAccountPanelTab = Tab
