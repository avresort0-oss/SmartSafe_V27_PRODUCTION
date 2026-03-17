import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
import os
import time
from datetime import datetime

from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    RADIUS,
    heading,
    body,
    SectionCard,
    StatCard,
    TabHeader,
    StatusBadge,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    StyledTextbox,
    apply_leadwave_theme,
)
from ui.theme.leadwave_components import CaptionLabel, TitleLabel
from core.api.whatsapp_baileys import BaileysAPI
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme.icon_registry import load_icon

class SendEngineTab(ctk.CTkFrame):
    """Single message sender with account-aware media support."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.api = BaileysAPI()
        self.selected_image_path = None
        self.view_state = "idle"  # idle, sending, success, error

        # Load icons
        try:
            self.success_icon = ctk.CTkImage(load_icon("success", (64, 64)), size=(64, 64))
            self.error_icon = ctk.CTkImage(load_icon("error", (64, 64)), size=(64, 64))
        except Exception:
            self.success_icon = None
            self.error_icon = None

        # Simple sending presets for retry / safety behavior
        self.send_profile = ctk.StringVar(value="Balanced")

        self._build_ui()
        # Bring this tab in line with the premium LeadWave theming.
        apply_leadwave_theme(self)
        start_daemon(self._load_accounts)
        self._set_view_state("idle")

    def _build_ui(self):
        header = TabHeader(
            self,
            title="Single Sender PRO",
            subtitle="Account-aware message & media sending",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Status Badge
        self.status_badge = StatusBadge(header.actions, text="READY", tone="info")
        self.status_badge.pack(side="right")

        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Left Column
        left_col = ctk.CTkFrame(main, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
        left_col.pack_propagate(False)
        left_col.rowconfigure(1, weight=1)  # Message section expands
        left_col.columnconfigure(0, weight=1)

        # Config Card
        config_card = SectionCard(left_col)
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Message Configuration",
            font=heading(TYPOGRAPHY["h3"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        # Account
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Select Account",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.account_dropdown = ctk.CTkComboBox(config_card.inner_frame, values=["acc1"], width=200)
        self.account_dropdown.pack(fill="x", pady=(0, SPACING["sm"]))
        self.account_dropdown.set("acc1")

        # Number
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Recipient Number",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.number_entry = StyledInput(config_card.inner_frame, placeholder_text="+966500000000")
        self.number_entry.pack(fill="x", pady=(0, SPACING["sm"]))

        # Type
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Message Type",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.message_type = ctk.CTkSegmentedButton(config_card.inner_frame, values=["Text Only", "Text + Image", "Image Only"], command=self._on_type_change)
        self.message_type.pack(fill="x", pady=(0, SPACING["sm"]))
        self.message_type.set("Text Only")
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Text Only uses the message box. Image Only sends the media without text.",
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, SPACING["xs"]))

        # Sending presets (affect retries / pacing)
        preset_row = ctk.CTkFrame(config_card.inner_frame, fg_color="transparent")
        preset_row.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(preset_row, text="Sending Profile", font=body(TYPOGRAPHY["caption"], "bold")).pack(side="left")
        preset_seg = ctk.CTkSegmentedButton(
            preset_row,
            values=["Safe", "Balanced", "Aggressive"],
            variable=self.send_profile,
        )
        preset_seg.pack(side="right")
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Safe = more retries, slower. Aggressive = fastest, fewer retries.",
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", pady=(4, 0))

        # Message Body
        ctk.CTkLabel(
            config_card.inner_frame,
            text="Message Content",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        self.message_box = StyledTextbox(config_card.inner_frame, height=120)
        self.message_box.pack(fill="x", pady=(0, SPACING["sm"]))

        # Image Section (Hidden initially)
        self.image_section = ctk.CTkFrame(config_card.inner_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            self.image_section,
            text="Attachment",
            font=body(TYPOGRAPHY["caption"], "bold"),
        ).pack(anchor="w", pady=(0, SPACING["xxs"]))
        img_row = ctk.CTkFrame(self.image_section, fg_color="transparent")
        img_row.pack(fill="x")
        
        SecondaryButton(img_row, text="Browse Image", command=self._browse_image).pack(side="left", padx=(0, SPACING["xs"]))
        SecondaryButton(
            img_row,
            text="Clear",
            command=self._clear_image,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color=COLORS["text_inverse"],
        ).pack(side="left")
        
        self.img_filename_label = ctk.CTkLabel(self.image_section, text="No image selected", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
        self.img_filename_label.pack(anchor="w", pady=(4, 0))

        # Actions Card
        action_card = SectionCard(left_col)
        action_card.pack(fill="x")
        
        self.send_btn = PrimaryButton(action_card.inner_frame, text="SEND NOW", command=self._send_message)
        self.send_btn.pack(fill="x", pady=(0, SPACING["xs"]))
        
        btn_row = ctk.CTkFrame(action_card.inner_frame, fg_color="transparent")
        btn_row.pack(fill="x")
        SecondaryButton(btn_row, text="Test Connection", command=self._test_connection).pack(side="left", fill="x", expand=True, padx=(0, SPACING["xxs"]))
        SecondaryButton(btn_row, text="Clear All", command=self._clear_all).pack(side="left", fill="x", expand=True, padx=(SPACING["xxs"], 0))

        # Right Column
        right_col = ctk.CTkFrame(main, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
        right_col.rowconfigure(2, weight=1) # Log expands
        
        # Preview Card
        preview_card = SectionCard(right_col)
        preview_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(preview_card.inner_frame, text="Media Preview", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        self.preview_frame = ctk.CTkFrame(
            preview_card.inner_frame,
            height=200,
            fg_color=COLORS["surface_2"],
            corner_radius=RADIUS["md"],
        )
        self.preview_frame.pack(fill="x")
        self.preview_frame.pack_propagate(False)
        
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="No image selected", font=body(TYPOGRAPHY["body"]), text_color=COLORS["text_muted"])
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")

        # Stats Card
        stats_card = SectionCard(right_col)
        stats_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(stats_card.inner_frame, text="Session Statistics", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))

        # Use a dedicated container so we don't mix pack/grid within the same parent.
        self.stats_container = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
        self.stats_container.pack(fill="x", expand=True)
        self.stats_container.columnconfigure(0, weight=1)
        self.stats_container.grid_rowconfigure(0, weight=1)

        # --- Idle State ---
        self.stats_idle_frame = ctk.CTkFrame(self.stats_container, fg_color="transparent")
        self.stats_idle_frame.grid(row=0, column=0, sticky="nsew")
        stats_grid = ctk.CTkFrame(self.stats_idle_frame, fg_color="transparent")
        stats_grid.pack(fill="x", pady=(0, SPACING["sm"]))
        stats_grid.grid_columnconfigure((0, 1), weight=1)

        self.stat_sent = StatCard(stats_grid, "Sent", "0", "success")
        self.stat_sent.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.stat_failed = StatCard(stats_grid, "Failed", "0", "danger")
        self.stat_failed.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # --- Sending State ---
        self.stats_sending_frame = ctk.CTkFrame(self.stats_container, fg_color="transparent")
        self.stats_sending_frame.grid(row=0, column=0, sticky="nsew")
        sending_content = ctk.CTkFrame(self.stats_sending_frame, fg_color="transparent")
        sending_content.place(relx=0.5, rely=0.5, anchor="center")
        self.sending_progress = ctk.CTkProgressBar(sending_content, mode="indeterminate")
        self.sending_progress.pack()
        self.sending_label = CaptionLabel(sending_content, text="Sending message...")
        self.sending_label.pack(pady=(SPACING["sm"], 0))

        # --- Success State ---
        self.stats_success_frame = ctk.CTkFrame(self.stats_container, fg_color="transparent")
        self.stats_success_frame.grid(row=0, column=0, sticky="nsew")
        success_content = ctk.CTkFrame(self.stats_success_frame, fg_color="transparent")
        success_content.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(success_content, text="", image=self.success_icon).pack()
        TitleLabel(success_content, text="Message Sent!").pack(pady=(SPACING["sm"], 0))

        # --- Error State ---
        self.stats_error_frame = ctk.CTkFrame(self.stats_container, fg_color="transparent")
        self.stats_error_frame.grid(row=0, column=0, sticky="nsew")
        error_content = ctk.CTkFrame(self.stats_error_frame, fg_color="transparent")
        error_content.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(error_content, text="", image=self.error_icon).pack()
        self.error_title_label = TitleLabel(error_content, text="Send Failed", text_color=COLORS["danger"])
        self.error_title_label.pack(pady=(SPACING["sm"], 0))
        self.error_message_label = CaptionLabel(error_content, text="Error details here.", wraplength=250)
        self.error_message_label.pack(pady=(SPACING["xs"], 0))

        # Log Card
        log_card = SectionCard(right_col)
        log_card.pack(fill="both", expand=True)
        ctk.CTkLabel(log_card.inner_frame, text="Activity Log", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xs"]))
        
        self.log_box = StyledTextbox(log_card.inner_frame)
        self.log_box.pack(fill="both", expand=True)

    def _set_view_state(self, state: str, **kwargs):
        """Update the UI to show a specific state in the stats panel."""
        self.view_state = state
        
        # Hide all frames
        for frame in [self.stats_idle_frame, self.stats_sending_frame, self.stats_success_frame, self.stats_error_frame]:
            frame.grid_remove()

        if state == "idle":
            self.stats_idle_frame.grid()
        elif state == "sending":
            self.sending_label.configure(text=kwargs.get("text", "Sending message..."))
            self.sending_progress.start()
            self.stats_sending_frame.grid()
        elif state == "success":
            self.stats_success_frame.grid()
            # Revert to idle after a delay
            self.after(2500, lambda: self._set_view_state("idle"))
        elif state == "error":
            self.error_message_label.configure(text=kwargs.get("text", "An unknown error occurred."))
            self.stats_error_frame.grid()
            # Revert to idle after a delay
            self.after(5000, lambda: self._set_view_state("idle"))

    def _on_type_change(self, value):
        if value in ["Text + Image", "Image Only"]:
            self.image_section.pack(fill="x", pady=(0, SPACING["sm"]), after=self.message_box)
            if value == "Image Only":
                self.message_box.configure(height=60)
            else:
                self.message_box.configure(height=120)
        else:
            self.image_section.pack_forget()
            self.message_box.configure(height=120)

    def _browse_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")],
        )

        if not file_path:
            return

        self.selected_image_path = file_path
        filename = os.path.basename(file_path)
        self.img_filename_label.configure(text=f" {filename}")

        try:
            img = Image.open(file_path)
            img.thumbnail((280, 280))
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(280, 280))
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo
        except Exception as exc:
            self.img_filename_label.configure(text=f" Error: {exc}")

    def _clear_image(self):
        self.selected_image_path = None
        self.img_filename_label.configure(text="No image selected")
        self.preview_label.configure(image=None, text="No image selected")

    def _clear_all(self):
        self.number_entry.delete(0, "end")
        self.message_box.delete("1.0", "end")
        self._clear_image()

    def _test_connection(self):
        result = self.api.get_health()
        if result.get("ok"):
            self._log_activity("Connection OK", "success")
        else:
            self._log_activity(f"Not connected: {result.get('error')}", "error")

    def _get_selected_account(self):
        value = (self.account_dropdown.get() or "").strip()
        if not value:
            return "default"
        return value.split()[0]

    def _send_message(self):
        number = self.number_entry.get().strip()
        message = self.message_box.get("1.0", "end").strip()
        msg_type = self.message_type.get()

        if not number:
            self._log_activity("Please enter phone number", "error")
            return

        if msg_type == "Text Only" and not message:
            self._log_activity("Please enter message", "error")
            return

        if msg_type in ["Text + Image", "Image Only"] and not self.selected_image_path:
            self._log_activity("Please select an image", "error")
            return

        self.send_btn.configure(state="disabled", text="Sending...")

        # Use shared helper to keep UI thread responsive
        start_daemon(lambda: self._send_worker(number, message, msg_type))

    def _send_worker(self, number, message, msg_type):
        try:
            account = self._get_selected_account()
            profile = (self.send_profile.get() or "Balanced").lower()

            ui_dispatch(self, lambda: self._set_view_state("sending", text=f"Sending to {number}..."))

            # Map profile to retry strategy
            if profile == "safe":
                max_attempts = 3
            elif profile == "aggressive":
                max_attempts = 1
            else:  # Balanced
                max_attempts = 2

            attempt = 0
            last_error = None
            result = {}

            while attempt < max_attempts:
                attempt += 1
                if msg_type == "Text Only":
                    result = self.api.send_message(number, message, account=account)
                else:
                    caption = message if message else ""
                    result = self.api.send_message(number, caption, media_path=self.selected_image_path, account=account)

                if result.get("ok"):
                    break
                last_error = result.get("error") or "Unknown error"
                if attempt < max_attempts:
                    ui_dispatch(self, lambda: self._log_activity(f"Send failed, retrying ({attempt}/{max_attempts})...", "warning"))
                    time.sleep(2)

            if result.get("ok"):
                current_sent = int(self.stat_sent.value.cget("text"))
                ui_dispatch(self, lambda: self.stat_sent.set_value(str(current_sent + 1)))
                ui_dispatch(self, lambda: self._log_activity(f"Message sent to {number} via {account}", "success"))
                ui_dispatch(self, lambda: self._set_view_state("success"))
            else:
                current_failed = int(self.stat_failed.value.cget("text"))
                ui_dispatch(self, lambda: self.stat_failed.set_value(str(current_failed + 1)))
                ui_dispatch(self, lambda: self._log_activity(f"Failed: {last_error}", "error"))
                ui_dispatch(self, lambda: self._set_view_state("error", text=last_error))

        except Exception as exc:
            current_failed = int(self.stat_failed.value.cget("text"))
            ui_dispatch(self, lambda: self.stat_failed.set_value(str(current_failed + 1)))
            ui_dispatch(self, lambda: self._log_activity(f"Error: {exc}", "error"))
            ui_dispatch(self, lambda: self._set_view_state("error", text=str(exc)))
        finally:
            ui_dispatch(self, lambda: self.send_btn.configure(state="normal", text="SEND NOW"))

    def _log_activity(self, text, level="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {text}\n"
        self.log_box.insert("end", log_entry)
        self.log_box.see("end")

    def _load_accounts(self):
        result = self.api.get_accounts()
        if not result.get("ok"):
            return

        accounts = [item.get("account") for item in result.get("accounts", []) if item.get("account")]
        if not accounts:
            return

        def _apply():
            self.account_dropdown.configure(values=accounts)
            self.account_dropdown.set(result.get("current_account") or accounts[0])

        ui_dispatch(self, _apply)
