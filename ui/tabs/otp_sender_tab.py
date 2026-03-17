import customtkinter as ctk
import random
import string
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from datetime import datetime

from core.api.whatsapp_baileys import BaileysAPI
from core.utils.contacts import load_contacts_from_csv, normalize_phone
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    TabHeader,
    StatusBadge,
    heading,
    body,
    SectionCard,
    StatCard,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    StyledTextbox,
    apply_leadwave_theme,
)

class OTPSenderTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    self.api = BaileysAPI()
    self.sent_count = 0
    self.failed_count = 0
    self.bulk_total = 0

    # Bulk sending profile + pacing
    self.profile_var = ctk.StringVar(value="Safe")
    self._send_delay = 5.0
    self._ui_batch_size = 10
    self._bulk_started_at: float | None = None
    self._apply_profile(self.profile_var.get())
    
    self.build_ui()
    # Apply LeadWave theme so this tab matches other PRO modules.
    apply_leadwave_theme(self)
    start_daemon(self._load_accounts)
  
  def build_ui(self):
    header = TabHeader(
      self,
      title="OTP Sender PRO",
      subtitle="Single and bulk OTP delivery with profiles",
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
    
    # Left panel
    left_col = ctk.CTkFrame(main, fg_color="transparent")
    left_col.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
    left_col.grid_rowconfigure(2, weight=1)  # Bulk OTP card area expands
    left_col.grid_columnconfigure(0, weight=1)
    
    # OTP Settings Card
    settings_card = SectionCard(left_col)
    settings_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(settings_card.inner_frame, text="OTP Configuration", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    # Account Selector
    ctk.CTkLabel(settings_card.inner_frame, text="Sender Account:", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(0, 4))
    self.account_dropdown = ctk.CTkComboBox(settings_card.inner_frame, values=["acc1"], width=200)
    self.account_dropdown.pack(fill="x", pady=(0, SPACING["sm"]))

    # Sending profile
    profile_row = ctk.CTkFrame(settings_card.inner_frame, fg_color="transparent")
    profile_row.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(profile_row, text="Sending Profile", font=body(TYPOGRAPHY["body"], "bold")).pack(side="left", padx=(0, 8))
    profile_seg = ctk.CTkSegmentedButton(
        profile_row,
        values=["Safe", "Balanced", "Aggressive"],
        variable=self.profile_var,
        command=self._on_profile_change,
    )
    profile_seg.pack(side="right")

    # Length & Type row
    config_row = ctk.CTkFrame(settings_card.inner_frame, fg_color="transparent")
    config_row.pack(fill="x", pady=(0, 8))
    
    ctk.CTkLabel(config_row, text="Length:", font=body(TYPOGRAPHY["body"])).pack(side="left", padx=(0, 8))
    self.length_var = ctk.StringVar(value="6")
    ctk.CTkOptionMenu(config_row, values=["4", "5", "6", "7", "8"], variable=self.length_var, width=80).pack(side="left", padx=(0, 16))
    
    ctk.CTkLabel(config_row, text="Type:", font=body(TYPOGRAPHY["body"])).pack(side="left", padx=(0, 8))
    self.type_var = ctk.StringVar(value="Numeric")
    ctk.CTkOptionMenu(config_row, values=["Numeric", "Alphanumeric"], variable=self.type_var, width=120).pack(side="left")
    
    # Auto-generate toggle
    self.auto_gen = ctk.CTkCheckBox(settings_card.inner_frame, text="Auto-generate unique OTP per recipient")
    self.auto_gen.pack(anchor="w", pady=(8, 0))
    self.auto_gen.select()
    
    # Single OTP Card
    single_card = SectionCard(left_col)
    single_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(single_card.inner_frame, text="Single OTP Send", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    self.single_phone = StyledInput(single_card.inner_frame, placeholder_text="Phone Number (e.g. +880...)")
    self.single_phone.pack(fill="x", pady=(0, SPACING["sm"]))
    
    # Display Area
    display_frame = ctk.CTkFrame(single_card.inner_frame, fg_color=COLORS["surface_2"], corner_radius=8)
    display_frame.pack(fill="x", pady=(0, SPACING["sm"]))
    
    self.otp_display = ctk.CTkLabel(display_frame, text="------", font=heading(TYPOGRAPHY["h1"], "bold"), text_color=COLORS["brand"])
    self.otp_display.pack(pady=16)
    
    btn_row = ctk.CTkFrame(single_card.inner_frame, fg_color="transparent")
    btn_row.pack(fill="x")
    SecondaryButton(btn_row, text="Generate", command=self.generate_single_otp).pack(side="left", fill="x", expand=True, padx=(0, 4))
    PrimaryButton(btn_row, text="Send Now", command=self.send_single_otp).pack(side="left", fill="x", expand=True, padx=(4, 0))

    # Bulk OTP Card
    bulk_card = SectionCard(left_col)
    bulk_card.pack(fill="x")
    ctk.CTkLabel(bulk_card.inner_frame, text="Bulk OTP Send", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    SecondaryButton(bulk_card.inner_frame, text="Upload CSV File", command=self.upload_csv).pack(fill="x", pady=(0, 8))
    self.bulk_info = ctk.CTkLabel(bulk_card.inner_frame, text="No file selected", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.bulk_info.pack(anchor="w", pady=(0, SPACING["sm"]))
    self.bulk_source_info = ctk.CTkLabel(
      bulk_card.inner_frame,
      text="Source: -",
      font=body(TYPOGRAPHY["caption"]),
      text_color=COLORS["text_secondary"],
    )
    self.bulk_source_info.pack(anchor="w", pady=(0, SPACING["sm"]))
    
    PrimaryButton(bulk_card.inner_frame, text="Start Bulk Sending", command=self.send_bulk_otp).pack(fill="x")

    # Right panel
    right_col = ctk.CTkFrame(main, fg_color="transparent")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    
    # Stats Card
    stats_card = SectionCard(right_col)
    stats_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(stats_card.inner_frame, text="Statistics", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    stats_grid = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
    stats_grid.pack(fill="x")
    stats_grid.grid_columnconfigure((0, 1), weight=1)
    
    self.sent_stat = StatCard(stats_grid, "Sent", "0", "success")
    self.sent_stat.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    
    self.failed_stat = StatCard(stats_grid, "Failed", "0", "danger")
    self.failed_stat.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    # Bulk progress panel
    ctk.CTkLabel(stats_card.inner_frame, text="Bulk Progress", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(8, 4))
    self.bulk_progress = ctk.CTkProgressBar(stats_card.inner_frame, height=10)
    self.bulk_progress.pack(fill="x")
    self.bulk_progress.set(0)

    meta = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
    meta.pack(fill="x", pady=(6, 0))
    self.bulk_speed_label = ctk.CTkLabel(
        meta,
        text="Speed: – otp/min",
        font=body(TYPOGRAPHY["caption"]),
        text_color=COLORS["text_muted"],
    )
    self.bulk_speed_label.pack(side="left")
    self.bulk_eta_label = ctk.CTkLabel(
        meta,
        text="ETA: –",
        font=body(TYPOGRAPHY["caption"]),
        text_color=COLORS["text_muted"],
    )
    self.bulk_eta_label.pack(side="right")

    # Template Card
    template_card = SectionCard(right_col)
    template_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(template_card.inner_frame, text="Message Template", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, 4))
    ctk.CTkLabel(template_card.inner_frame, text="Variables: {code}, {name}", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["info"]).pack(anchor="w", pady=(0, 8))
    
    self.template_box = StyledTextbox(template_card.inner_frame, height=100)
    self.template_box.pack(fill="x")
    self.template_box.insert("1.0", "Your OTP verification code is: {code}\nValid for 5 minutes.\nDo not share with anyone.")
    
    # Log Card
    log_card = SectionCard(right_col)
    log_card.pack(fill="both", expand=True)
    
    log_header = ctk.CTkFrame(log_card.inner_frame, fg_color="transparent")
    log_header.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(log_header, text="Activity Log", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    SecondaryButton(log_header, text="Clear", command=self.clear_log, width=60, height=24).pack(side="right")
    
    self.log_box = StyledTextbox(log_card.inner_frame)
    self.log_box.pack(fill="both", expand=True)
  
  def _load_accounts(self):
    """Load accounts from API"""
    result = self.api.get_accounts()
    if not result.get("ok"):
        return

    accounts = [item.get("account") for item in result.get("accounts", []) if item.get("account")]
    if accounts:
        def _update():
            self.account_dropdown.configure(values=accounts)
            self.account_dropdown.set(result.get("current_account") or accounts[0])
        ui_dispatch(self, _update)

  def generate_otp(self):
    """Generate OTP based on settings"""
    length = int(self.length_var.get())
    otp_type = self.type_var.get()
    
    if otp_type == "Numeric":
      return ''.join(random.choices(string.digits, k=length))
    else:
      return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
  
  def generate_single_otp(self):
    """Generate and display OTP"""
    otp = self.generate_otp()
    self.otp_display.configure(text=otp)
  
  def send_single_otp(self):
    """Send OTP to single number"""
    phone_input = self.single_phone.get().strip()
    otp = self.otp_display.cget("text")
    
    if not phone_input:
      messagebox.showwarning("Warning", "Please enter phone number!")
      return
    
    if otp == "------":
      messagebox.showwarning("Warning", "Please generate OTP first!")
      return
    
    normalized = normalize_phone(phone_input)
    if not normalized:
      messagebox.showwarning("Warning", "Please enter a valid phone number!")
      return

    threading.Thread(target=self._send_single, args=(normalized, otp), daemon=True).start()
  
  def _send_single(self, phone, otp):
    """Send single OTP in background"""
    template = self.template_box.get("1.0", "end").strip()
    account = self.account_dropdown.get()
    message = template.replace("{code}", otp).replace("{name}", "User")
    
    self.add_log(f" Sending OTP to {phone} via {account}...")
    
    res = self.api.send_message(phone, message, account=account)
    
    if res.get("ok", False):
      self.sent_count += 1
      ui_dispatch(self, lambda: self.sent_stat.set_value(str(self.sent_count)))
      ui_dispatch(self, lambda: self.add_log(f" OTP sent successfully! Code: {otp}", "success"))
    else:
      self.failed_count += 1
      ui_dispatch(self, lambda: self.failed_stat.set_value(str(self.failed_count)))
      error = res.get("error", "Unknown error")
      ui_dispatch(self, lambda: self.add_log(f" Failed: {error}", "error"))
  
  def upload_csv(self):
    """Upload CSV for bulk sending"""
    file_path = filedialog.askopenfilename(
      title="Select CSV File",
      filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    
    if not file_path:
      return
    
    try:
      normalized = load_contacts_from_csv(file_path)
      contacts = [
        {
          "phone": c.phone,
          "name": c.name,
          "account": c.account,
          **(c.extra or {}),
        }
        for c in normalized
      ]
      self.load_external_contacts(contacts, f"CSV: {Path(file_path).name}")

    except Exception as e:
      messagebox.showerror("Error", f"Failed to load CSV: {str(e)}")

  def load_external_contacts(self, contacts, source_label: str, *, account: str | None = None):
    """Load bulk OTP recipients from another tab without requiring CSV."""
    self.bulk_contacts = [dict(item) for item in (contacts or []) if isinstance(item, dict)]
    if account:
      try:
        self.account_dropdown.set(str(account))
      except Exception:
        pass

    inactive = sum(1 for c in self.bulk_contacts if str(c.get("profile_status") or "").strip().lower() == "inactive")
    failed_checks = sum(1 for c in self.bulk_contacts if c.get("profile_error"))

    self.bulk_info.configure(text=f" Loaded {len(self.bulk_contacts)} contacts")
    self.bulk_source_info.configure(
      text=f"Source: {source_label} | Inactive: {inactive} | Check errors: {failed_checks}"
    )
    self.add_log(f" Loaded {len(self.bulk_contacts)} contacts for bulk OTP from {source_label}", "info")
  
  def send_bulk_otp(self):
    """Send OTP to all contacts in CSV"""
    if not hasattr(self, 'bulk_contacts') or not self.bulk_contacts:
      messagebox.showwarning("Warning", "Please load contacts first!")
      return
    
    if not messagebox.askyesno("Confirm", f"Send OTP to {len(self.bulk_contacts)} contacts?"):
      return
    
    # Reset bulk metrics for this run
    self.bulk_total = len(self.bulk_contacts)
    self._bulk_started_at = time.time()
    ui_dispatch(self, lambda: self.bulk_progress.set(0))

    threading.Thread(target=self._send_bulk, daemon=True).start()
  
  def _send_bulk(self):
    """Send bulk OTP in background"""
    template = self.template_box.get("1.0", "end").strip()
    selected_account = self.account_dropdown.get()

    delay = float(self._send_delay or 0)
    batch_size = max(1, int(self._ui_batch_size or 1))
    processed_since_ui = 0
    processed_total = 0
    start_ts = self._bulk_started_at or time.time()
    last_ui_ts = start_ts

    for idx, contact in enumerate(self.bulk_contacts):
      phone = contact.get('phone', contact.get('number', '')).strip()
      name = contact.get('name', 'User')

      normalized_phone = normalize_phone(phone)
      if not normalized_phone:
        ui_dispatch(self, lambda p=phone: self.add_log(f" Skipping invalid number: {p}", "warning"))
        continue
      
      # Generate unique OTP if auto-generate enabled
      if self.auto_gen.get():
        otp = self.generate_otp()
      else:
        otp = self.generate_otp()
      
      message = template.replace("{code}", otp).replace("{name}", name)
      
      ui_dispatch(self, lambda p=normalized_phone, o=otp: self.add_log(f" Sending to {p} via {selected_account}..."))
      
      res = self.api.send_message(normalized_phone, message, account=selected_account)
      
      if res.get("ok", False):
        self.sent_count += 1
        ui_dispatch(self, lambda: self.sent_stat.set_value(str(self.sent_count)))
        ui_dispatch(self, lambda p=phone: self.add_log(f" Sent to {p}", "success"))
      else:
        self.failed_count += 1
        ui_dispatch(self, lambda: self.failed_stat.set_value(str(self.failed_count)))
        ui_dispatch(self, lambda p=phone: self.add_log(f" Failed: {p}", "error"))

      processed_since_ui += 1
      processed_total += 1
      now = time.time()

      # Batch UI progress updates
      if (
          processed_since_ui >= batch_size
          or (now - last_ui_ts) >= 1.0
          or idx == len(self.bulk_contacts) - 1
      ):
        self._update_bulk_progress(processed_total, now - start_ts)
        processed_since_ui = 0
        last_ui_ts = now

      if delay > 0:
        time.sleep(delay)
    
    ui_dispatch(self, lambda: self.add_log(f"\n Bulk OTP sending completed!", "success"))
    ui_dispatch(self, lambda: messagebox.showinfo("Complete", f"Sent: {self.sent_count}\nFailed: {self.failed_count}"))

  def add_log(self, message, level="info"):
    """Add log entry to activity log"""
    if not hasattr(self, "log_box"):
      return
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    self.log_box.insert("end", entry)
    self.log_box.see("end")

  def clear_log(self):
    """Clear activity log"""
    if hasattr(self, "log_box"):
      self.log_box.delete("1.0", "end")

  # --- Preset + progress helpers ---

  def _on_profile_change(self, value: str):
    self._apply_profile(value)

  def _apply_profile(self, profile: str):
    """
    Map friendly presets to pacing + batching.

    Safe: slower, friendlier to WhatsApp rate limits.
    Balanced: good default for most use.
    Aggressive: faster but higher risk of blocks.
    """
    name = (profile or "").lower()
    if name == "safe":
      self._send_delay = 5.0
      self._ui_batch_size = 5
    elif name == "aggressive":
      self._send_delay = 0.5
      self._ui_batch_size = 25
    else:  # Balanced / fallback
      self._send_delay = 2.0
      self._ui_batch_size = 10

  def _update_bulk_progress(self, processed: int, elapsed: float):
    total = max(1, self.bulk_total or len(getattr(self, "bulk_contacts", []) or []))
    remaining = max(0, total - processed)
    progress = processed / total

    per_min = 0.0
    if elapsed > 0:
      per_min = (processed / elapsed) * 60.0

    speed_display = "–"
    eta_display = "–"
    if per_min > 0 and processed > 0:
      speed_display = f"{per_min:.1f}"
      if remaining > 0:
        minutes_left = remaining / per_min
        if minutes_left < 1:
          eta_display = "< 1 min"
        else:
          eta_display = f"{minutes_left:.1f} min"

    def _apply():
      self.bulk_progress.set(progress)
      self.bulk_speed_label.configure(text=f"Speed: {speed_display} otp/min")
      self.bulk_eta_label.configure(text=f"ETA: {eta_display}")

    ui_dispatch(self, _apply)
