import customtkinter as ctk
from tkinter import filedialog, messagebox
import csv
import os
import time
from datetime import datetime
import zlib

from core.api.whatsapp_baileys import BaileysAPI
from core.engine.account_health import AUTO_ROTATE_ACCOUNT_SENTINEL
from core.engine.engine_service import get_engine_service
from core.utils.contacts import load_contacts_from_csv, normalize_phone
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
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
from ui.utils.threading_helpers import start_daemon, ui_dispatch

class MultiEngineTab(ctk.CTkFrame):
  """Enhanced Multi Engine with Bulk Image Support & Account Rotation"""
  
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    
    # Initialize
    self.api = BaileysAPI()
    self.engine_service = get_engine_service()
    self.contacts = []
    self.is_running = False
    self.is_paused = False
    self.active_job_id: str | None = None
    self.current_index = 0
    self.stats = {"total": 0, "sent": 0, "failed": 0}
    # Simple snapshot for the shared system status board
    self._last_system_sent = 0
    self._last_system_ts: float | None = None
    self._last_audit_payload: dict | None = None
    
    self._build_ui()
    # Apply LeadWave theming so this tab matches the refreshed shell.
    apply_leadwave_theme(self)
    start_daemon(self._load_accounts)
    
  @staticmethod
  def _crc32_text(text: str) -> int:
    try:
      return int(zlib.crc32((text or "").encode("utf-8")) & 0xFFFFFFFF)
    except Exception:
      return 0

  def _audit_is_fresh(self, payload: dict, *, profile_name: str, message_template: str, max_age_s: int = 15 * 60) -> bool:
    """
    Best-effort "freshness" gate so START runs an audit when inputs changed.
    """
    if not isinstance(payload, dict) or not payload.get("ok"):
      return False

    inputs = payload.get("inputs", {}) or {}
    if (inputs.get("profile_name") or payload.get("profile")) != profile_name:
      return False

    msg_crc = int(inputs.get("message_crc32", -1))
    if msg_crc != self._crc32_text(message_template):
      return False

    # Contacts: compare total count and (when present) sample signature.
    rows_total = int((payload.get("contacts", {}) or {}).get("rows_total", -1))
    if rows_total != len(self.contacts):
      return False

    # Age gate: audit includes `generated_at` (UTC ISO). If missing, treat as stale.
    generated_at = payload.get("generated_at")
    if not generated_at:
      return False
    try:
      # ISO without timezone → assume UTC.
      dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
      age = (datetime.utcnow() - dt.replace(tzinfo=None)).total_seconds()
      if age > float(max_age_s):
        return False
    except Exception:
      return False

    return True

  def _build_ui(self):
    header = TabHeader(
      self,
      title="Multi Engine PRO",
      subtitle="Bulk campaign sending with safety audit",
    )
    header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

    # Status Badge
    self.status_badge = StatusBadge(header.actions, text="READY", tone="success")
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
    left_col.grid_rowconfigure(1, weight=1)  # Message card expands
    left_col.grid_columnconfigure(0, weight=1)
    
    # Right panel
    right_col = ctk.CTkFrame(main, fg_color="transparent")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    
    # --- Left Column Content ---
    
    # 1. Settings Card
    settings_card = SectionCard(left_col)
    settings_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(
      settings_card.inner_frame,
      text="Campaign Settings",
      font=heading(TYPOGRAPHY["h3"], "bold"),
    ).pack(anchor="w", pady=(0, SPACING["xxs"]))

    # CSV & contacts section
    ctk.CTkLabel(
      settings_card.inner_frame,
      text="Contacts & CSV",
      font=body(TYPOGRAPHY["caption"], "bold"),
      text_color=COLORS["text_secondary"],
    ).pack(anchor="w", pady=(SPACING["xs"], SPACING["xxs"]))
    
    # CSV Upload
    csv_row = ctk.CTkFrame(settings_card.inner_frame, fg_color="transparent")
    csv_row.pack(fill="x", pady=(0, SPACING["xs"]))
    
    SecondaryButton(csv_row, text="Upload CSV", command=self._upload_csv, width=100).pack(side="left", padx=(0, SPACING["xs"]))
    SecondaryButton(csv_row, text="Clean", command=self._clean_csv, width=80).pack(side="left", padx=(0, SPACING["xs"]))
    
    self.csv_label = ctk.CTkLabel(csv_row, text="No file selected", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.csv_label.pack(side="left", padx=SPACING["xxs"])
    
    self.contacts_count = ctk.CTkLabel(csv_row, text="", font=body(TYPOGRAPHY["caption"], "bold"), text_color=COLORS["success"])
    self.contacts_count.pack(side="left", padx=SPACING["xxs"])
    self.contacts_source = ctk.CTkLabel(
      settings_card.inner_frame,
      text="Source: -",
      font=body(TYPOGRAPHY["caption"]),
      text_color=COLORS["text_secondary"],
    )
    self.contacts_source.pack(anchor="w", pady=(0, SPACING["xs"]))
    # Account & Speed
    ctk.CTkLabel(
      settings_card.inner_frame,
      text="Routing & Speed",
      font=body(TYPOGRAPHY["caption"], "bold"),
      text_color=COLORS["text_secondary"],
    ).pack(anchor="w", pady=(SPACING["sm"], SPACING["xxs"]))

    opts_row = ctk.CTkFrame(settings_card.inner_frame, fg_color="transparent")
    opts_row.pack(fill="x", pady=(0, SPACING["xs"]))
    
    self.account_dropdown = ctk.CTkComboBox(opts_row, values=["Main Account", "Auto Rotate", "Account 2", "Account 3"], width=140)
    self.account_dropdown.pack(side="left", padx=(0, SPACING["xs"]), fill="x", expand=True)
    self.account_dropdown.set("Main Account")
    
    self.speed_mode = ctk.CTkSegmentedButton(opts_row, values=["Safe", "Medium", "Fast"])
    self.speed_mode.pack(side="right")
    self.speed_mode.set("Safe")
    
    # Message Type
    type_row = ctk.CTkFrame(settings_card.inner_frame, fg_color="transparent")
    type_row.pack(fill="x")
    ctk.CTkLabel(type_row, text="Message Type:", font=body(TYPOGRAPHY["caption"], "bold")).pack(side="left", padx=(0, SPACING["xs"]))
    self.message_type = ctk.CTkSegmentedButton(type_row, values=["Text", "Text+Image", "Image"], command=self._on_type_change)
    self.message_type.pack(side="left", fill="x", expand=True)
    self.message_type.set("Text")
    
    # 2. Message Card
    msg_card = SectionCard(left_col)
    msg_card.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
    ctk.CTkLabel(msg_card.inner_frame, text="Message Content", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    ctk.CTkLabel(msg_card.inner_frame, text="Variables: {name}, {phone}, {code}", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["info"]).pack(anchor="w", pady=(0, SPACING["xs"]))
    
    self.message_box = StyledTextbox(msg_card.inner_frame, height=120)
    self.message_box.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
    
    # Image Section (Hidden by default)
    self.image_section = ctk.CTkFrame(msg_card.inner_frame, fg_color="transparent")
    
    ctk.CTkLabel(self.image_section, text="Image Settings", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xs"]))
    
    self.image_mode = ctk.CTkSegmentedButton(self.image_section, values=["Single Image", "CSV Column"])
    self.image_mode.pack(fill="x", pady=(0, 8))
    self.image_mode.set("Single Image")
    
    img_act_row = ctk.CTkFrame(self.image_section, fg_color="transparent")
    img_act_row.pack(fill="x")
    SecondaryButton(img_act_row, text="Browse Image", command=self._browse_image).pack(side="left", padx=(0, 8))
    self.image_file_label = ctk.CTkLabel(img_act_row, text="No image", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.image_file_label.pack(side="left")
    
    # AI Variation Checkbox
    self.ai_variation = ctk.CTkCheckBox(msg_card.inner_frame, text="AI Message Variation")
    self.ai_variation.pack(anchor="w", pady=(0, 8))

    # 3. Safety Audit (Preflight)
    audit_card = SectionCard(left_col)
    audit_card.pack(fill="x", pady=(0, SPACING["sm"]))

    audit_header = ctk.CTkFrame(audit_card.inner_frame, fg_color="transparent")
    audit_header.pack(fill="x", pady=(0, 6))

    ctk.CTkLabel(
      audit_header,
      text="Safety Audit (Preflight)",
      font=heading(TYPOGRAPHY["h3"], "bold"),
    ).pack(side="left")

    self.audit_btn = SecondaryButton(audit_header, text="Run Audit", command=self._run_preflight_audit, width=100, height=28)
    self.audit_btn.pack(side="right")

    self.audit_status = ctk.CTkLabel(
      audit_card.inner_frame,
      text="Run an audit before START to see hygiene + schedule + predicted risk.",
      font=body(TYPOGRAPHY["caption"]),
      text_color=COLORS["text_muted"],
    )
    self.audit_status.pack(anchor="w", pady=(0, SPACING["xs"]))

    self.audit_box = StyledTextbox(audit_card.inner_frame, height=140, font=(TYPOGRAPHY["mono"], 12))
    self.audit_box.pack(fill="x")
    self.audit_box.insert("end", "No audit has been run yet.\n")

    # 4. Controls Card
    ctrl_card = SectionCard(left_col)
    ctrl_card.pack(fill="x")
    
    self.start_btn = PrimaryButton(ctrl_card.inner_frame, text="START CAMPAIGN", command=self._start_sending)
    self.start_btn.pack(fill="x", pady=(0, SPACING["xs"]))
    
    ctrl_row = ctk.CTkFrame(ctrl_card.inner_frame, fg_color="transparent")
    ctrl_row.pack(fill="x")
    self.pause_btn = SecondaryButton(ctrl_row, text="Pause", command=self._pause_sending, state="disabled")
    self.pause_btn.pack(side="left", fill="x", expand=True, padx=(0, SPACING["xxs"]))
    self.stop_btn = SecondaryButton(
      ctrl_row,
      text="Stop",
      command=self._stop_sending,
      state="disabled",
      fg_color=COLORS["danger"],
      hover_color=COLORS["danger"],
      text_color=COLORS["text_inverse"],
    )
    self.stop_btn.pack(side="left", fill="x", expand=True, padx=(SPACING["xxs"], 0))

    self.duplicate_btn = SecondaryButton(ctrl_card.inner_frame, text="Duplicate Campaign", command=self._duplicate_campaign)
    self.duplicate_btn.pack(fill="x", pady=(SPACING["xs"], 0))

    # --- Right Column Content ---
    
    # 0. System Status Board (shared across management tabs)
    system_card = SectionCard(right_col)
    system_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(
      system_card.inner_frame,
      text="System Status Board",
      font=heading(TYPOGRAPHY["h3"], "bold"),
      text_color=COLORS["text_secondary"],
    ).pack(anchor="w", pady=(0, SPACING["xs"]))

    sys_grid = ctk.CTkFrame(system_card.inner_frame, fg_color="transparent")
    sys_grid.pack(fill="x")
    sys_grid.grid_columnconfigure((0, 1, 2), weight=1)

    self.sys_accounts = StatCard(sys_grid, "Accounts Active", "0/0", "info")
    self.sys_accounts.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xxs"]))

    self.sys_engine_load = StatCard(sys_grid, "Engine Load (msg/min)", "-", "success")
    self.sys_engine_load.grid(row=0, column=1, sticky="ew", padx=SPACING["xxs"])

    self.sys_queue = StatCard(sys_grid, "Queue Length", "0", "warning")
    self.sys_queue.grid(row=0, column=2, sticky="ew", padx=(SPACING["xxs"], 0))

    actions_row = ctk.CTkFrame(system_card.inner_frame, fg_color="transparent")
    actions_row.pack(fill="x", pady=(8, 0))
    actions_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

    # One-click engine controls: start/stop all, rebalance, resync.
    PrimaryButton(
      actions_row,
      text="Start All",
      command=self._start_all_engines,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
    SecondaryButton(
      actions_row,
      text="Stop All",
      command=self._stop_all_engines,
    ).grid(row=0, column=1, sticky="ew", padx=4)
    SecondaryButton(
      actions_row,
      text="Rebalance Load",
      command=self._rebalance_engines,
    ).grid(row=0, column=2, sticky="ew", padx=4)
    SecondaryButton(
      actions_row,
      text="Resync Now",
      command=self._refresh_system_status,
    ).grid(row=0, column=3, sticky="ew", padx=(4, 0))

    # 1. Stats Card
    stats_card = SectionCard(right_col)
    stats_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(stats_card.inner_frame, text="Campaign Statistics", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    stats_grid = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
    stats_grid.pack(fill="x")
    stats_grid.grid_columnconfigure((0, 1), weight=1)
    
    self.stat_total = StatCard(stats_grid, "Total", "0", "info")
    self.stat_total.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 8))
    self.stat_remaining = StatCard(stats_grid, "Remaining", "0", "warning")
    self.stat_remaining.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 8))
    
    self.stat_sent = StatCard(stats_grid, "Sent", "0", "success")
    self.stat_sent.grid(row=1, column=0, sticky="ew", padx=(0, 4))
    self.stat_failed = StatCard(stats_grid, "Failed", "0", "danger")
    self.stat_failed.grid(row=1, column=1, sticky="ew", padx=(4, 0))
    
    ctk.CTkLabel(stats_card.inner_frame, text="Progress", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(12, 4))
    self.progress_bar = ctk.CTkProgressBar(stats_card.inner_frame, height=10)
    self.progress_bar.pack(fill="x")
    self.progress_bar.set(0)
    self.progress_text = ctk.CTkLabel(stats_card.inner_frame, text="0%", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.progress_text.pack(anchor="e")

    # 2. Log Card
    log_card = SectionCard(right_col)
    log_card.pack(fill="both", expand=True)
    
    log_header = ctk.CTkFrame(log_card.inner_frame, fg_color="transparent")
    log_header.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(log_header, text="Live Log", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    
    export_frame = ctk.CTkFrame(log_header, fg_color="transparent")
    export_frame.pack(side="right")
    self.retry_btn = SecondaryButton(export_frame, text="Retry Failed", command=self._retry_failed, width=80, height=24, state="disabled")
    self.retry_btn.pack(side="left", padx=(0, 4))
    SecondaryButton(export_frame, text="Export Failed", command=self._export_failed, width=80, height=24).pack(side="left", padx=(0, 4))
    SecondaryButton(export_frame, text="Clear All", command=self._clear_log, width=80, height=24).pack(side="left")
    
    self.log_box = StyledTextbox(log_card.inner_frame, font=(TYPOGRAPHY["mono"], 12))
    self.log_box.pack(fill="both", expand=True)

  def _load_accounts(self):
    """Load available accounts from the Node API into the dropdown."""
    result = self.api.get_accounts()
    if not result.get("ok"):
      return

    accounts = []
    for item in result.get("accounts", []) or []:
      name = item.get("account") or item.get("name")
      if name:
        accounts.append(str(name))

    if not accounts:
      return

    # Preserve current selection if possible.
    current = self.account_dropdown.get()
    values = ["Main Account", "Auto Rotate"] + accounts

    def _apply():
      self.account_dropdown.configure(values=values)
      if current in values:
        self.account_dropdown.set(current)
      else:
        self.account_dropdown.set("Main Account")

    ui_dispatch(self, _apply)
  
  def _on_type_change(self, value):
    """Handle message type change"""
    if value in ["Text+Image", "Image"]:
      self.image_section.pack(fill="x", pady=(0, SPACING["sm"]), after=self.message_box)
    else:
      self.image_section.pack_forget()

  def _browse_image(self):
    file_path = filedialog.askopenfilename(
      title="Select Image",
      filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")]
    )
    if file_path:
      filename = os.path.basename(file_path)
      self.image_file_label.configure(text=filename)
      self._log(f"Selected image: {filename}")
  
  def _upload_csv(self):
    """Upload CSV file"""
    file_path = filedialog.askopenfilename(
      title="Select CSV File",
      filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    
    if file_path:
      try:
        normalized_contacts = load_contacts_from_csv(file_path)
        contacts = [
          {
            "phone": c.phone,
            "name": c.name,
            "account": c.account,
            **(c.extra or {}),
          }
          for c in normalized_contacts
        ]
        self.load_external_contacts(contacts, f"CSV: {os.path.basename(file_path)}")

      except Exception as e:
        self.csv_label.configure(text=f" Error: {str(e)}")
        self._log(f" CSV Error: {str(e)}")

  def load_external_contacts(self, contacts, source_label: str, *, account: str | None = None):
    """Load contacts pushed from another tab or source."""
    self.contacts = [dict(item) for item in (contacts or []) if isinstance(item, dict)]
    if account:
      try:
        self.account_dropdown.set(str(account))
      except Exception:
        pass

    inactive = sum(1 for c in self.contacts if str(c.get("profile_status") or "").strip().lower() == "inactive")
    failed_checks = sum(1 for c in self.contacts if c.get("profile_error"))

    self.csv_label.configure(text=f" {source_label}")
    self.contacts_count.configure(text=f"{len(self.contacts)} contacts")
    self.contacts_source.configure(
      text=f"Source: {source_label} | Inactive: {inactive} | Check errors: {failed_checks}"
    )

    self.stats["total"] = len(self.contacts)
    self.stat_total.set_value(str(len(self.contacts)))
    self.stat_remaining.set_value(str(len(self.contacts)))
    self._last_audit_payload = None

    self._log(f"Loaded {len(self.contacts)} contacts from {source_label}")
  
  def _clean_csv(self):
    """Clean and format numbers"""
    if not self.contacts:
      self._log(" No contacts loaded")
      return
    
    cleaned = 0
    for contact in self.contacts:
      raw = contact.get("phone") or contact.get("number")
      normalized = normalize_phone(raw)
      if not normalized:
        continue
      # Preserve the user-facing "+" prefix while keeping the underlying
      # value canonicalized for the engine/Node layer.
      contact["phone"] = f"+{normalized}"
      cleaned += 1

    self._log(f" Cleaned {cleaned} numbers")
  
  def _get_profile_name(self) -> str:
    """Map UI speed mode to engine profile name."""
    value = (self.speed_mode.get() or "Safe").strip().lower()
    if value == "medium":
      return "balanced"
    if value == "fast":
      return "aggressive"
    return "safe"

  def _format_audit_report(self, payload: dict) -> str:
    if not payload or not payload.get("ok"):
      return f"Audit failed: {payload.get('error') if isinstance(payload, dict) else 'Unknown error'}\n"

    contacts = payload.get("contacts", {}) or {}
    pacing = payload.get("pacing", {}) or {}
    risk = payload.get("risk", {}) or {}
    schedule = payload.get("schedule", {}) or {}
    hist = payload.get("recipient_history", {}) or {}

    suggestions = payload.get("suggestions", []) or []
    factors = risk.get("factors", {}) or {}

    lines: list[str] = []
    lines.append(f"Profile: {payload.get('profile') or '-'} | Mode: {payload.get('mode') or '-'}")
    lines.append(f"Predicted risk: {risk.get('label')} ({risk.get('score')}/100)")
    lines.append("")
    lines.append("Contacts hygiene")
    lines.append(f"- Total rows: {contacts.get('rows_total', 0)}")
    lines.append(f"- Valid: {contacts.get('valid', 0)} | Invalid: {contacts.get('invalid', 0)}")
    lines.append(f"- Unique: {contacts.get('unique', 0)} | Duplicates: {contacts.get('duplicates', 0)}")
    lines.append("")
    lines.append("Pacing & caps")
    lines.append(f"- Avg delay (est): {pacing.get('avg_delay_s', '-')}s")
    lines.append(f"- Est throughput: {pacing.get('estimated_msgs_per_min', '-')} msg/min")
    lines.append(f"- Est duration: {pacing.get('estimated_duration_min', '-')} min (~{pacing.get('estimated_duration_hr', '-')} hr)")
    lines.append(f"- Limits: {pacing.get('minute_limit', '-')}/min, {pacing.get('hourly_limit', '-')}/hr, {pacing.get('daily_limit', '-')}/day")
    if int(pacing.get("spill_hours_estimate", 0) or 0) >= 2:
      lines.append(f"- Hotspot: likely spans ~{pacing.get('spill_hours_estimate')} hours due to hourly caps")
    if int(pacing.get("spill_days_estimate", 0) or 0) >= 2:
      lines.append(f"- Hotspot: likely spans ~{pacing.get('spill_days_estimate')} days due to daily caps")
    lines.append("")
    lines.append("Schedule")
    lines.append(f"- Current hour: {schedule.get('current_hour', '-')} | Time-window risk: {schedule.get('time_window_risk', '-')}")
    lines.append("")
    lines.append("Recipient history (sampled)")
    if hist.get("store_enabled"):
      lines.append(f"- Sample: {hist.get('sample_size', 0)} | Known: {hist.get('known', 0)} | New: {hist.get('new', 0)}")
      lines.append(f"- Blocked now: {hist.get('blocked_now', 0)}")
      examples = hist.get("blocked_examples", []) or []
      for ex in examples[:3]:
        lines.append(f"  • {ex}")
    else:
      lines.append("- Persistent store disabled/unavailable (known/new ratio not computed).")
    lines.append("")
    lines.append("Risk factors (predicted)")
    for k, v in factors.items():
      lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("Fix suggestions")
    if suggestions:
      for s in suggestions:
        lines.append(f"- {s}")
    else:
      lines.append("- No urgent issues detected for this profile.")

    return "\n".join(lines).strip() + "\n"

  def _run_preflight_audit(self):
    if self.is_running:
      self._log(" Audit is disabled while a campaign is running")
      return

    if not self.contacts:
      self._log(" Please upload CSV first (audit needs contacts)")
      return

    message = self.message_box.get("1.0", "end").strip()
    if not message:
      self._log(" Please enter message (audit needs the message template)")
      return

    profile_name = self._get_profile_name()
    started_at = datetime.now().strftime("%H:%M:%S")

    self.audit_btn.configure(state="disabled")
    self.audit_status.configure(text=f"Running audit... ({started_at})")

    def _worker():
      try:
        payload = self.engine_service.run_preflight_audit(
          contacts=self.contacts,
          message_template=message,
          profile_name=profile_name,
        )
      except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

      report = self._format_audit_report(payload)

      def _apply():
        self._last_audit_payload = payload if isinstance(payload, dict) else None
        self.audit_box.delete("1.0", "end")
        self.audit_box.insert("end", report)
        if payload.get("ok"):
          label = payload.get("risk", {}).get("label", "-")
          score = payload.get("risk", {}).get("score", "-")
          self.audit_status.configure(text=f"Last audit: {started_at} | Predicted risk: {label} ({score}/100)")
          self._log(f" Preflight audit complete: {label} ({score}/100)")
        else:
          self.audit_status.configure(text=f"Audit failed: {payload.get('error')}")
          self._log(f" Audit failed: {payload.get('error')}")
        self.audit_btn.configure(state="normal")

      ui_dispatch(self, _apply)

    start_daemon(_worker)

  def _confirm_if_risky(self, payload: dict) -> bool:
    """
    Return True if user confirms proceeding when audit looks risky.
    """
    if not isinstance(payload, dict) or not payload.get("ok"):
      return True

    risk = payload.get("risk", {}) or {}
    label = str(risk.get("label") or "").upper().strip()
    score = risk.get("score")

    contacts = payload.get("contacts", {}) or {}
    invalid = int(contacts.get("invalid", 0) or 0)
    duplicates = int(contacts.get("duplicates", 0) or 0)

    schedule = payload.get("schedule", {}) or {}
    in_quiet = bool(schedule.get("in_quiet_hours_now"))

    is_high = label in {"HIGH", "CRITICAL"} or (isinstance(score, int) and score >= 70)
    has_hygiene_issues = (invalid + duplicates) > 0

    if not (is_high or has_hygiene_issues or in_quiet):
      return True

    lines = [
      "Preflight Safety Audit warnings detected.",
      "",
      f"- Predicted risk: {label or '-'} ({score}/100)" if score is not None else f"- Predicted risk: {label or '-'}",
      f"- Invalid: {invalid} | Duplicates: {duplicates}",
    ]
    if in_quiet:
      lines.append("- Quiet Hours: currently active (sending will be blocked/paused).")
    lines.append("")
    lines.append("Proceed anyway?")

    return messagebox.askyesno("Safety Audit Warning", "\n".join(lines))

  def _start_engine_job(self, *, message: str, profile_name: str):
    """
    Start bulk sending via shared EngineService (assumes inputs are validated).
    """
    # Reset UI state
    self.is_running = True
    self.is_paused = False
    self.current_index = 0
    self.stats = {"total": len(self.contacts), "sent": 0, "failed": 0}

    self.start_btn.configure(state="disabled")
    self.pause_btn.configure(state="normal", text="Pause")
    self.stop_btn.configure(state="normal")
    self.retry_btn.configure(state="disabled")

    self._log(" Starting bulk send via engine...")

    def _on_status(message: str):
      ui_dispatch(self, lambda: self._log(f" {message}"))

    def _on_progress(completed: int, total: int):
      def _apply():
        engine_stats = self.engine_service.get_engine_stats() or {}
        sent = int(engine_stats.get("sent", 0) or 0)
        failed = int(engine_stats.get("failed", 0) or 0)

        self.stats["total"] = int(total or len(self.contacts))
        self.stats["sent"] = sent
        self.stats["failed"] = failed

        remaining = max(0, self.stats["total"] - (sent + failed))
        self.stat_total.set_value(str(self.stats["total"]))
        self.stat_sent.set_value(str(sent))
        self.stat_failed.set_value(str(failed))
        self.stat_remaining.set_value(str(remaining))

        progress = (sent + failed) / self.stats["total"] if self.stats["total"] > 0 else 0
        self.progress_bar.set(progress)
        self.progress_text.configure(text=f"{int(progress * 100)}%")

      ui_dispatch(self, _apply)

    def _on_complete(payload: dict):
      def _apply():
        sent = int(payload.get("sent", self.stats.get("sent", 0)) or 0)
        failed = int(payload.get("failed", self.stats.get("failed", 0)) or 0)
        total = int(payload.get("total", self.stats.get("total", len(self.contacts))) or 0)

        self.stats["total"] = total
        self.stats["sent"] = sent
        self.stats["failed"] = failed

        remaining = max(0, total - (sent + failed))
        self.stat_total.set_value(str(total))
        self.stat_sent.set_value(str(sent))
        self.stat_failed.set_value(str(failed))
        self.stat_remaining.set_value(str(remaining))

        success_rate = (sent / total * 100) if total > 0 else 0.0

        self.is_running = False
        self.is_paused = False
        self.active_job_id = None

        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="Pause")
        self.stop_btn.configure(state="disabled")
        if failed > 0:
          self.retry_btn.configure(state="normal")

        self._log(f"\n Completed!")
        self._log(f" Total: {total}")
        self._log(f" Sent: {sent}")
        self._log(f" Failed: {failed}")
        self._log(f" Success Rate: {success_rate:.1f}%")

      ui_dispatch(self, _apply)

    result = self.engine_service.start_bulk_job(
      contacts=self.contacts,
      message_template=message,
      profile_name=profile_name,
      metadata={
        "source": "multi_engine_tab",
        "ai_variation": (lambda v: bool(int(v)) if str(v).strip().isdigit() else bool(v))(self.ai_variation.get()),
      },
      status_callback=_on_status,
      progress_callback=_on_progress,
      completion_callback=_on_complete,
    )

    if not result.get("ok"):
      self.is_running = False
      self._log(f" Failed to start engine job: {result.get('error')}")
      self.start_btn.configure(state="normal")
      self.pause_btn.configure(state="disabled", text="Pause")
      self.stop_btn.configure(state="disabled")
      return

    self.active_job_id = result.get("job_id")

  def _start_sending(self):
    """Start bulk sending via shared EngineService."""
    if not self.contacts:
      self._log(" Please load contacts first")
      return
    
    message = self.message_box.get("1.0", "end").strip()
    if not message and self.message_type.get() != "Image":
      self._log(" Please enter message")
      return

    profile_name = self._get_profile_name()

    # Apply UI routing choice into contact payloads.
    selected_account = (self.account_dropdown.get() or "").strip()
    if selected_account:
      lowered = selected_account.strip().lower()
      if lowered == "auto rotate":
        for c in self.contacts:
          c["account"] = AUTO_ROTATE_ACCOUNT_SENTINEL
      elif lowered == "main account":
        # Preserve per-row account from CSV (or Node default if missing).
        pass
      else:
        for c in self.contacts:
          c["account"] = selected_account

    # Preflight audit should happen *before* START. If missing/outdated, run it now.
    if not self._audit_is_fresh(self._last_audit_payload or {}, profile_name=profile_name, message_template=message):
      self._log(" Running preflight Safety Audit before starting…")
      self.start_btn.configure(state="disabled")
      self.audit_btn.configure(state="disabled")
      self.audit_status.configure(text="Running audit before START…")

      def _worker():
        try:
          payload = self.engine_service.run_preflight_audit(
            contacts=self.contacts,
            message_template=message,
            profile_name=profile_name,
          )
        except Exception as exc:
          payload = {"ok": False, "error": str(exc)}

        report = self._format_audit_report(payload)

        def _apply():
          self._last_audit_payload = payload if isinstance(payload, dict) else None
          self.audit_box.delete("1.0", "end")
          self.audit_box.insert("end", report)

          self.audit_btn.configure(state="normal")
          self.start_btn.configure(state="normal")

          if not payload.get("ok"):
            self.audit_status.configure(text=f"Audit failed: {payload.get('error')}")
            self._log(f" Audit failed: {payload.get('error')}")
            return

          label = payload.get("risk", {}).get("label", "-")
          score = payload.get("risk", {}).get("score", "-")
          self.audit_status.configure(text=f"Last audit: {datetime.now().strftime('%H:%M:%S')} | Predicted risk: {label} ({score}/100)")

          if not self._confirm_if_risky(payload):
            self._log(" Start cancelled (audit warning not acknowledged)")
            return

          self._start_engine_job(message=message, profile_name=profile_name)

        ui_dispatch(self, _apply)

      start_daemon(_worker)
      return

    # Audit is fresh; still confirm if it predicts high risk.
    if not self._confirm_if_risky(self._last_audit_payload or {}):
      self._log(" Start cancelled (audit warning not acknowledged)")
      return

    self._start_engine_job(message=message, profile_name=profile_name)

  def _start_all_engines(self):
    """
    One-click helper mapped to the existing bulk send flow.
    If a campaign is already running, this is a no-op.
    """
    if not self.is_running:
      self._log("▶ Start All engines requested from control board")
      self._start_sending()

  def _stop_all_engines(self):
    """One-click helper to stop any active campaign."""
    if self.is_running:
      self._log("⏹ Stop All engines requested from control board")
    self._stop_sending()

  def _rebalance_engines(self):
    """
    Lightweight 'rebalance' that prefers accounts with fewer errors and more messages
    based on live /stats, updating the account dropdown ordering.
    """
    def _worker():
      try:
        stats_resp = self.api.get_stats()
        stats = stats_resp.get("stats", {}) or {}
      except Exception as exc:
        self._log(f" Rebalance error: {exc}")
        return

      if not stats:
        self._log(" No stats available to rebalance accounts")
        return

      ranked = sorted(
        stats.items(),
        key=lambda item: (
          # Prefer connected accounts with higher volume and fewer errors
          not bool(item[1].get("connected")),
          -int(item[1].get("messages_sent", 0) or 0),
          int(item[1].get("errors", 0) or 0),
        ),
      )
      ordered_accounts = [name for name, _row in ranked]

      def _apply():
        values = ["Auto Rotate"] + ordered_accounts
        self.account_dropdown.configure(values=values)
        if not self.account_dropdown.get() or self.account_dropdown.get() not in values:
          self.account_dropdown.set("Auto Rotate")
        self._log(" Rebalanced engine account order from live stats")

      ui_dispatch(self, _apply)

    start_daemon(_worker)
  
  def _pause_sending(self):
    """Pause or resume the active engine job."""
    if not self.active_job_id:
      self._log(" No active campaign to pause/resume")
      return

    stats = self.engine_service.get_engine_stats() or {}
    is_paused = bool(stats.get("is_paused"))

    if is_paused:
      if self.engine_service.resume_job(self.active_job_id):
        self.is_paused = False
        self.pause_btn.configure(text="Pause")
        self._log("▶ Resumed")
    else:
      if self.engine_service.pause_job(self.active_job_id):
        self.is_paused = True
        self.pause_btn.configure(text="Resume")
        self._log("⏸ Paused")
  
  def _stop_sending(self):
    """Stop the active engine job and reset controls."""
    if self.active_job_id:
      self.engine_service.stop_job(self.active_job_id)

    self.is_running = False
    self.is_paused = False
    self.active_job_id = None
    
    self.start_btn.configure(state="normal")
    self.pause_btn.configure(state="disabled", text="Pause")
    self.stop_btn.configure(state="disabled")
    
    self._log("⏹ Stopped by user")

  def _duplicate_campaign(self):
    """Reset stats and logs to prepare for a duplicate run."""
    if self.is_running:
      messagebox.showwarning("Warning", "Cannot duplicate while campaign is running.")
      return

    # Reset stats
    self.stats = {"total": len(self.contacts), "sent": 0, "failed": 0}
    self.stat_total.set_value(str(len(self.contacts)))
    self.stat_sent.set_value("0")
    self.stat_failed.set_value("0")
    self.stat_remaining.set_value(str(len(self.contacts)))
    self.progress_bar.set(0)
    self.progress_text.configure(text="0%")
    
    # Clear log
    self.log_box.configure(state="normal")
    self.log_box.delete("1.0", "end")
    self.log_box.configure(state="disabled")
    
    self._log("Campaign duplicated. Ready to start.")
  
  def _clear_log(self):
    """Clear the activity log"""
    self.log_box.configure(state="normal")
    self.log_box.delete("1.0", "end")
    self.log_box.configure(state="disabled")

  def _retry_failed(self):
    """Retry sending to failed contacts from the last run."""
    failed_contacts = self.engine_service.get_failed_contacts()
    if not failed_contacts:
      self._log(" No failed contacts to retry")
      return

    self._log(f" Retrying {len(failed_contacts)} failed contacts...")
    # Load failed contacts as the new list and restart
    self.contacts = list(failed_contacts)
    self.stats = {"total": len(self.contacts), "sent": 0, "failed": 0}
    self._start_sending()

  def _export_failed(self):
    """Export failed contacts to CSV."""
    failed = self.engine_service.get_failed_contacts()
    if not failed:
      self._log(" No failed contacts to export")
      return

    path = filedialog.asksaveasfilename(
      defaultextension=".csv",
      filetypes=[("CSV files", "*.csv")],
      title="Export Failed Contacts"
    )
    if path:
      try:
        # Re-use the contacts utility or simple csv writer
        keys = failed[0].keys() if failed else ["phone", "name"]
        with open(path, 'w', newline='', encoding='utf-8') as f:
          writer = csv.DictWriter(f, fieldnames=keys)
          writer.writeheader()
          writer.writerows(failed)
        self._log(f" Exported {len(failed)} failed contacts")
      except Exception as e:
        self._log(f" Export failed: {e}")

  def _log(self, message):
    """Add log entry"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    self.log_box.insert("end", log_entry)
    self.log_box.see("end")

  def _refresh_system_status(self):
    """Refresh the shared system status board using Baileys /stats."""
    def _worker():
      try:
        resp = self.api.get_stats()
      except Exception as exc:
        self._log(f" System status error: {exc}")
        return

      if not resp.get("ok"):
        self._log(f" System status error: {resp.get('error')}")
        return

      stats = resp.get("stats", {}) or {}
      total_accounts = len(stats)
      active_accounts = 0
      total_sent = 0
      total_errors = 0

      for row in stats.values():
        if row.get("connected"):
          active_accounts += 1
        total_sent += int(row.get("messages_sent", 0) or 0)
        total_errors += int(row.get("errors", 0) or 0)

      # Queue length is optional; fall back to 0 if missing.
      queue_len = int(resp.get("queue_length", 0) or resp.get("queue", 0) or 0)

      # Approximate engine throughput in messages/min based on deltas.
      now = time.time()
      per_min = "-"
      if self._last_system_ts is not None:
        elapsed = max(0.1, now - self._last_system_ts)
        delta_sent = max(0, total_sent - self._last_system_sent)
        per_min = f"{(delta_sent / elapsed) * 60.0:.1f}"
      self._last_system_ts = now
      self._last_system_sent = total_sent

      def _apply():
        self.sys_accounts.set_value(f"{active_accounts}/{total_accounts}")
        self.sys_engine_load.set_value(per_min)
        self.sys_queue.set_value(str(queue_len))

      ui_dispatch(self, _apply)

    start_daemon(_worker)
