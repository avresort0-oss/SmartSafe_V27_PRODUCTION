import customtkinter as ctk
import zipfile
import os
import threading
from tkinter import messagebox
from datetime import datetime
from core.api.whatsapp_baileys import BaileysAPI
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
    StyledTextbox,
    apply_leadwave_theme,
)
from ui.utils.threading_helpers import ui_dispatch

class CloudSyncTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    
    self.api = BaileysAPI()
    self.build_ui()
    # Harmonize backup UI with the LeadWave dashboard theme.
    apply_leadwave_theme(self)
    self.log_activity("Cloud Sync module initialized.")

  def build_ui(self):
    header = TabHeader(
      self,
      title="Backup & Sync PRO",
      subtitle="Local backups and system snapshots",
    )
    header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

    # Status Badge
    self.status_badge = StatusBadge(header.actions, text="READY", tone="info")
    self.status_badge.pack(side="right")
    
    # Main container
    main = ctk.CTkFrame(self, fg_color="transparent")
    main.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
    main.grid_columnconfigure(0, weight=1) # Left
    main.grid_columnconfigure(1, weight=1) # Right
    main.grid_rowconfigure(0, weight=1)
    
    # Left panel
    left_col = ctk.CTkFrame(main, fg_color="transparent")
    left_col.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
    left_col.grid_rowconfigure(3, weight=1)  # Actions card area expands
    left_col.grid_columnconfigure(0, weight=1)
    
    # Status Card
    status_card = SectionCard(left_col)
    status_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(status_card.inner_frame, text="Backup Status", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    stats_grid = ctk.CTkFrame(status_card.inner_frame, fg_color="transparent")
    stats_grid.pack(fill="x")
    stats_grid.grid_columnconfigure((0, 1), weight=1)
    
    self.status_stat = StatCard(stats_grid, "Status", "Idle", "info")
    self.status_stat.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xxs"]))
    
    self.last_sync_stat = StatCard(stats_grid, "Last Backup", "Never", "neutral")
    self.last_sync_stat.grid(row=0, column=1, sticky="ew", padx=(SPACING["xxs"], 0))

    # System Status Board (mirrors the management tabs overview)
    system_card = SectionCard(left_col)
    system_card.pack(fill="x", pady=(SPACING["sm"], SPACING["sm"]))
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

    self.sys_queue = StatCard(sys_grid, "Queue Length", "0", "warning")
    self.sys_queue.grid(row=0, column=1, sticky="ew", padx=SPACING["xxs"])

    self.sys_sync = StatCard(sys_grid, "Sync State", "Idle", "success")
    self.sys_sync.grid(row=0, column=2, sticky="ew", padx=(SPACING["xxs"], 0))
    
    # Config Card
    config_card = SectionCard(left_col)
    config_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(config_card.inner_frame, text="Configuration", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    ctk.CTkLabel(config_card.inner_frame, text="Backup Location", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    provider_menu = ctk.CTkOptionMenu(config_card.inner_frame, values=["Local Storage (backups/)", "Google Drive (Coming Soon)"])
    provider_menu.pack(fill="x", pady=(0, SPACING["sm"]))
    
    ctk.CTkLabel(config_card.inner_frame, text="Auto-Backup", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    freq_menu = ctk.CTkOptionMenu(config_card.inner_frame, values=["Manual Only", "Daily", "Weekly"])
    freq_menu.pack(fill="x", pady=(0, SPACING["sm"]))
    
    ctk.CTkLabel(config_card.inner_frame, text="Data to Sync", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    ctk.CTkCheckBox(config_card.inner_frame, text="Templates").pack(anchor="w", pady=2)
    ctk.CTkCheckBox(config_card.inner_frame, text="Balancer Accounts").pack(anchor="w", pady=2)
    ctk.CTkCheckBox(config_card.inner_frame, text="Auto-Reply Rules").pack(anchor="w", pady=2)
    
    # Actions Card
    actions_card = SectionCard(left_col)
    actions_card.pack(fill="x")
    PrimaryButton(
        actions_card.inner_frame,
        text="Resync Now (Create Local Backup)",
        command=self.sync_now,
    ).pack(fill="x", pady=(0, SPACING["xs"]))
    SecondaryButton(
        actions_card.inner_frame,
        text="Open Backup Folder",
        command=self.open_backup_folder,
    ).pack(fill="x", pady=(0, SPACING["xs"]))
    SecondaryButton(
        actions_card.inner_frame,
        text="Refresh System Status",
        command=self.refresh_system_status,
    ).pack(fill="x")
    
    # Right panel
    right_col = ctk.CTkFrame(main, fg_color="transparent")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    
    log_card = SectionCard(right_col)
    log_card.pack(fill="both", expand=True)
    ctk.CTkLabel(log_card.inner_frame, text="Activity Log", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xs"]))
    self.log_box = StyledTextbox(log_card.inner_frame)
    self.log_box.pack(fill="both", expand=True)

  def sync_now(self):
    threading.Thread(target=self._perform_backup, daemon=True).start()

  def _perform_backup(self):
    try:
        ui_dispatch(self, lambda: self.status_stat.set_value("Backing up...", "warning"))
        ui_dispatch(self, lambda: self.log_activity("Starting local backup..."))
        
        if not os.path.exists("backups"):
            os.makedirs("backups")
        
        filename = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        with zipfile.ZipFile(filename, 'w') as zip_file:
            # Add config files
            for file in os.listdir('.'):
                if file.endswith('.json'):
                    zip_file.write(file)
                    
            # Add logs
            if os.path.exists('logs'):
                for root, dirs, files in os.walk('logs'):
                    for file in files:
                        zip_file.write(os.path.join(root, file))
        
        ui_dispatch(self, lambda: self.status_stat.set_value("Idle", "success"))
        ui_dispatch(self, lambda: self.last_sync_stat.set_value(datetime.now().strftime("%H:%M")))
        ui_dispatch(self, lambda: self.log_activity(f"Backup created: {filename}", "success"))
        ui_dispatch(self, lambda: messagebox.showinfo("Success", f"Backup saved to {filename}"))
        
    except Exception as e:
        ui_dispatch(self, lambda: self.status_stat.set_value("Error", "danger"))
        ui_dispatch(self, lambda: self.log_activity(f"Backup failed: {str(e)}", "error"))

  def open_backup_folder(self):
    if not os.path.exists("backups"):
        os.makedirs("backups")
    os.startfile("backups")

  def log_activity(self, message, level="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    self.log_box.insert("end", log_entry)
    self.log_box.see("end")

  def refresh_system_status(self):
    """
    Refresh the compact system status board to keep this tab aligned with
    the other management views (accounts / queue / sync).
    """

    def _worker():
      try:
        resp = self.api.get_stats()
      except Exception as exc:
        ui_dispatch(self, lambda: self.log_activity(f"Status refresh failed: {exc}", "error"))
        return

      if not resp.get("ok"):
        ui_dispatch(
          self,
          lambda: self.log_activity(f"Status refresh failed: {resp.get('error')}", "error"),
        )
        return

      stats = resp.get("stats", {}) or {}
      total_accounts = len(stats)
      active_accounts = 0
      for row in stats.values():
        if row.get("connected"):
          active_accounts += 1

      queue_len = int(resp.get("queue_length", 0) or resp.get("queue", 0) or 0)

      def _apply():
        self.sys_accounts.set_value(f"{active_accounts}/{total_accounts}")
        self.sys_queue.set_value(str(queue_len))
        # Sync state here reflects backup subsystem; mirror the high-level status.
        self.sys_sync.set_value(self.status_stat.value.cget("text") if hasattr(self.status_stat, "value") else "Idle")

      ui_dispatch(self, _apply)

    threading.Thread(target=_worker, daemon=True).start()
