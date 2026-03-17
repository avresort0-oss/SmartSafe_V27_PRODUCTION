import customtkinter as ctk
import threading
import time
import json
import os
from tkinter import messagebox
from datetime import datetime
from core.engine.risk_brain import RiskBrain
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
    StatCard,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    apply_leadwave_theme,
)

class BalancerTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    
    # State
    self.api = BaileysAPI()
    self.accounts_file = "accounts_config.json"
    self.accounts = self.load_accounts()
    self.accounts_lock = threading.Lock()
    self.monitoring_active = False
    self.stop_event = threading.Event()
    
    # Load balancing strategies
    self.strategies = {
      "round_robin": "Round Robin (Equal Distribution)",
      "least_used": "Least Used (Smart Balance)",
      "health_based": "Health Based (Best Performance)",
      "random": "Random Selection"
    }
    
    self.build_ui()
    # Harmonize this legacy tab with the premium LeadWave shell.
    apply_leadwave_theme(self)
    self.refresh_accounts()
    self.start_monitoring()
  
  def build_ui(self):
    header = TabHeader(
      self,
      title="Balancer PRO",
      subtitle="Account load balancing, health, and monitoring",
    )
    header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

    # Status Badge
    self.status_badge = StatusBadge(header.actions, text="ACTIVE", tone="success")
    self.status_badge.pack(side="right")
    
    # Main Container
    main_container = ctk.CTkFrame(self, fg_color="transparent")
    main_container.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
    main_container.grid_columnconfigure(0, weight=3) # Left panel wider
    main_container.grid_columnconfigure(1, weight=2)
    main_container.grid_rowconfigure(0, weight=1)
    
    # Left Panel - Account List
    left_panel = SectionCard(main_container)
    left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
    left_panel.grid_rowconfigure(1, weight=1)  # Accounts list expands
    left_panel.grid_columnconfigure(0, weight=1)
    
    # Accounts Header
    accounts_header = ctk.CTkFrame(left_panel.inner_frame, fg_color="transparent")
    accounts_header.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(accounts_header, text="Connected Accounts", font=heading(TYPOGRAPHY["h2"], "bold")).pack(side="left")
    SecondaryButton(accounts_header, text="Sync from Connected", command=self.sync_from_api, width=140).pack(side="right", padx=(SPACING["xs"], 0))
    PrimaryButton(accounts_header, text="Add Account", command=self.add_account_dialog, width=120).pack(side="right")
    
    # Accounts List
    self.accounts_container = ctk.CTkScrollableFrame(left_panel.inner_frame, fg_color=COLORS["surface_2"], corner_radius=RADIUS["md"])
    self.accounts_container.pack(fill="both", expand=True)
    
    # Right Panel - Stats & Controls (Scrollable)
    right_panel = ctk.CTkScrollableFrame(main_container, fg_color="transparent")
    right_panel.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))

    # System Status Board (central view shared with other management tabs)
    system_card = SectionCard(right_panel)
    system_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(
        system_card.inner_frame,
        text="System Status Board",
        font=heading(TYPOGRAPHY["h3"], "bold"),
        text_color=COLORS["text_secondary"],
    ).pack(anchor="w", pady=(0, 6))

    sys_grid = ctk.CTkFrame(system_card.inner_frame, fg_color="transparent")
    sys_grid.pack(fill="x")
    sys_grid.grid_columnconfigure((0, 1), weight=1)

    self.sys_accounts_stat = StatCard(sys_grid, "Accounts (active/total)", "0/0", "info")
    self.sys_accounts_stat.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xs"]))

    self.sys_health_stat = StatCard(sys_grid, "Avg Health", "0%", "success")
    self.sys_health_stat.grid(row=0, column=1, sticky="ew", padx=(SPACING["xs"], 0))

    self.sys_risky_stat = StatCard(sys_grid, "High‑risk", "0", "warning")
    self.sys_risky_stat.grid(row=1, column=0, sticky="ew", padx=(0, SPACING["xs"]), pady=(SPACING["xs"], 0))

    self.sys_queue_stat = StatCard(sys_grid, "Queue Length", "0", "neutral")
    self.sys_queue_stat.grid(row=1, column=1, sticky="ew", padx=(SPACING["xs"], 0), pady=(SPACING["xs"], 0))
    
    # Overall Stats
    stats_card = SectionCard(right_panel)
    stats_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(stats_card.inner_frame, text="Overall Statistics", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, 6))
    stats_grid = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
    stats_grid.pack(fill="x")
    stats_grid.grid_columnconfigure((0,1,2), weight=1)
    self.total_accounts_stat = StatCard(stats_grid, "Total", "0", "info")
    self.total_accounts_stat.grid(row=0, column=0, sticky="ew", padx=(0, 2))
    self.active_accounts_stat = StatCard(stats_grid, "Active", "0", "success")
    self.active_accounts_stat.grid(row=0, column=1, sticky="ew", padx=2)
    self.blocked_accounts_stat = StatCard(stats_grid, "Issues", "0", "danger")
    self.blocked_accounts_stat.grid(row=0, column=2, sticky="ew", padx=(2, 0))

    # Strategy Selector
    strategy_card = SectionCard(right_panel)
    strategy_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(strategy_card.inner_frame, text="Balancing Strategy", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, 6))
    self.strategy_var = ctk.StringVar(value="health_based")
    strategy_menu = ctk.CTkOptionMenu(strategy_card.inner_frame, 
                     values=list(self.strategies.values()),
                     variable=self.strategy_var,
                     width=200,
                     height=28)
    strategy_menu.pack(fill="x")
    
    # Global Settings
    settings_card = SectionCard(right_panel)
    settings_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(settings_card.inner_frame, text="Global Settings", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, 6))
    self.auto_failover = ctk.CTkCheckBox(settings_card.inner_frame, text="Auto Failover (switch on failure)", font=body(TYPOGRAPHY["caption"]))
    self.auto_failover.pack(anchor="w", pady=2)
    self.auto_failover.select()
    self.auto_pause_risky = ctk.CTkCheckBox(settings_card.inner_frame, text="Auto pause high-risk accounts", font=body(TYPOGRAPHY["caption"]))
    self.auto_pause_risky.pack(anchor="w", pady=2)
    self.auto_pause_risky.select()
    self.auto_reactivate = ctk.CTkCheckBox(settings_card.inner_frame, text="Auto reactivate after cooldown", font=body(TYPOGRAPHY["caption"]))
    self.auto_reactivate.pack(anchor="w", pady=2)
    self.auto_reactivate.select()
    
    # Global Actions / One‑click controls
    actions_card = SectionCard(right_panel)
    actions_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(
        actions_card.inner_frame,
        text="One‑click Actions",
        font=heading(TYPOGRAPHY["h3"], "bold"),
    ).pack(anchor="w", pady=(0, 6))
    actions_grid = ctk.CTkFrame(actions_card.inner_frame, fg_color="transparent")
    actions_grid.pack(fill="x")
    actions_grid.grid_columnconfigure((0, 1), weight=1)

    # Start / stop all maps to activate / pause for the balancer.
    PrimaryButton(
        actions_grid,
        text="Start All",
        command=self.activate_all,
        height=26,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
    SecondaryButton(
        actions_grid,
        text="Stop All",
        command=self.pause_all,
        height=26,
    ).grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)

    SecondaryButton(
        actions_grid,
        text="Rebalance Load",
        command=self.rebalance_load,
        height=26,
    ).grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=2)
    SecondaryButton(
        actions_grid,
        text="Resync Now",
        command=self.resync_now,
        height=26,
    ).grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=2)

    SecondaryButton(
        actions_grid,
        text="Reset Stats",
        command=self.reset_all_stats,
        height=26,
    ).grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=2)
    PrimaryButton(
        actions_grid,
        text="Save Config",
        command=self.save_accounts,
        height=26,
    ).grid(row=2, column=1, sticky="ew", padx=(2, 0), pady=2)
    
    # Activity Log
    log_card = SectionCard(right_panel)
    log_card.pack(fill="both", expand=True, pady=0)
    log_header = ctk.CTkFrame(log_card.inner_frame, fg_color="transparent")
    log_header.pack(fill="x", pady=(0, 6))
    ctk.CTkLabel(log_header, text="Activity Log", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    SecondaryButton(log_header, text="Clear", command=self.clear_log, width=80, height=26).pack(side="right")
    self.log_box = ctk.CTkTextbox(log_card.inner_frame, font=body(TYPOGRAPHY["mono"]))
    self.log_box.pack(fill="both", expand=True)
  
  def load_accounts(self):
    """Load accounts from config file"""
    if os.path.exists(self.accounts_file):
      try:
        with open(self.accounts_file, 'r') as f:
          data = json.load(f)
          return data
      except:
        return []
    return []

  def sync_from_api(self):
    """Sync accounts from Baileys API"""
    res = self.api.get_accounts()
    if not res.get("ok"):
        messagebox.showerror("Error", "Could not fetch accounts from API")
        return

    api_accounts = res.get("accounts", [])
    added = 0
    with self.accounts_lock:
        existing_names = {a['name'] for a in self.accounts}

        for acc in api_accounts:
            name = acc.get("account")
            if name and name not in existing_names:
                new_acc = {
                    "name": name,
                    "phone": "Unknown",
                    "instance_id": 0,
                    "status": "active",
                    "health_score": 100,
                    "sent_today": 0,
                    "success_rate": 100,
                    "risk_score": 0,
                    "last_activity": "Just now"
                }
                self.accounts.append(new_acc)
                added += 1
    
    if added > 0:
        self.save_accounts()
        self.refresh_accounts()
        messagebox.showinfo("Success", f"Synced {added} new accounts from API!")
    else:
        messagebox.showinfo("Info", "No new accounts found to sync.")
  
  def save_accounts(self):
    """Save accounts to config file"""
    try:
      with self.accounts_lock:
        with open(self.accounts_file, 'w') as f:
          json.dump(self.accounts, f, indent=2)
      
      messagebox.showinfo("Success", "Configuration saved successfully!")
      self.add_log(" Configuration saved", "success")
    except Exception as e:
      messagebox.showerror("Error", f"Failed to save: {str(e)}")
  
  def refresh_accounts(self):
    """Refresh account cards display"""
    # Clear existing cards
    for widget in self.accounts_container.winfo_children():
      widget.destroy()
    
    with self.accounts_lock:
        if not self.accounts:
          ctk.CTkLabel(self.accounts_container, 
                text="No accounts configured.\nClick 'Add Account' to start.",
                font=body(TYPOGRAPHY["body"]), text_color=COLORS["text_muted"]).pack(pady=50, padx=20)
          return
        
        # Create account cards
        for account in self.accounts:
          self.create_account_card(account)
    
    self.update_stats()
    self.update_system_status_board()
  
  def create_account_card(self, account):
    """Create a single account card"""
    # Main card
    card = ctk.CTkFrame(self.accounts_container, fg_color=COLORS["surface_1"], 
              border_width=1, border_color=COLORS["border"],
              corner_radius=RADIUS["lg"])
    card.pack(fill="x", pady=6, padx=8)
    
    # Header row
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=15, pady=(15, 5))
    
    # Account name and status
    name_frame = ctk.CTkFrame(header, fg_color="transparent")
    name_frame.pack(side="left")
    
    ctk.CTkLabel(name_frame, text=account['name'], font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    
    # Status indicator
    status_colors = {
      "active": (COLORS["success"], "●"),
      "paused": (COLORS["warning"], "●"),
      "blocked": (COLORS["danger"], "●"),
      "offline": (COLORS["text_muted"], "●")
    }
    
    color, symbol = status_colors.get(account.get('status', 'offline'), ("#666666", "●"))
    
    status_label = ctk.CTkLabel(name_frame, text=f" {symbol} {account.get('status', 'offline').upper()}", 
                  font=body(TYPOGRAPHY["caption"], "bold"), text_color=color)
    status_label.pack(side="left", padx=10)
    
    # Priority badge
    if account.get('priority', False):
      ctk.CTkLabel(name_frame, text="⭐ PRIORITY", 
            font=body(TYPOGRAPHY["caption"], "bold"), text_color=COLORS["warning"],
            fg_color=f"{COLORS['warning']}20", corner_radius=RADIUS["sm"],
            padx=8, pady=2).pack(side="left", padx=5)
    
    # Actions
    action_frame = ctk.CTkFrame(header, fg_color="transparent")
    action_frame.pack(side="right")
    
    # Toggle active/pause button
    toggle_text = "⏸" if account.get('status') == 'active' else "▶"
    toggle_btn = SecondaryButton(action_frame, text=toggle_text, width=35, height=28,
                                 command=lambda a=account: self.toggle_account(a))
    toggle_btn.pack(side="left", padx=2)
    
    edit_btn = SecondaryButton(action_frame, text="✏️", width=35, height=28,
                               command=lambda a=account: self.edit_account(a))
    edit_btn.pack(side="left", padx=2)
    
    delete_btn = SecondaryButton(action_frame, text="🗑️", width=35, height=28,
                                 command=lambda a=account: self.delete_account(a))
    delete_btn.pack(side="left", padx=2)
    
    # Info row
    info_frame = ctk.CTkFrame(card, fg_color="transparent")
    info_frame.pack(fill="x", padx=15, pady=5)
    
    ctk.CTkLabel(info_frame, text=f" {account.get('phone', 'N/A')}", 
          font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"]).pack(side="left")
    
    ctk.CTkLabel(info_frame, text=f" | Instance {account.get('instance_id', 'N/A')}", 
          font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"]).pack(side="left", padx=15)
    
    # Health bar
    health_frame = ctk.CTkFrame(card, fg_color="transparent")
    health_frame.pack(fill="x", padx=15, pady=5)
    
    health_score = account.get('health_score', 100)
    
    health_label = ctk.CTkFrame(health_frame, fg_color="transparent")
    health_label.pack(fill="x")
    
    ctk.CTkLabel(health_label, text=" Health:", 
          font=("Segoe UI", 11)).pack(side="left")
    
    # Health color
    if health_score >= 80:
      health_color = "#00ff00"
    elif health_score >= 50:
      health_color = "#ffaa00"
    else:
      health_color = "#ff3333"
    
    ctk.CTkLabel(health_label, text=f"{health_score}%", 
          font=("Segoe UI", 11, "bold"), 
          text_color=health_color).pack(side="right")
    
    # Health bar background
    health_bar_bg = ctk.CTkFrame(card, fg_color="#1a1a1a", 
                   corner_radius=5, height=8)
    health_bar_bg.pack(fill="x", padx=15, pady=(2, 5))
    
    # Health bar fill
    health_bar_fill = ctk.CTkFrame(health_bar_bg, fg_color=health_color, corner_radius=5)
    health_bar_fill.place(relx=0, rely=0, relwidth=(health_score / 100 if health_score > 0 else 0), relheight=1)
    
    # Stats row
    stats_row = ctk.CTkFrame(card, fg_color="#1a1a1a", corner_radius=8)
    stats_row.pack(fill="x", padx=15, pady=(5, 10))
    stats_row.grid_columnconfigure((0, 1, 2), weight=1)
    
    # Messages sent today
    stat_col1 = ctk.CTkFrame(stats_row, fg_color="transparent")
    stat_col1.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
    
    ctk.CTkLabel(stat_col1, text="Sent Today", 
          font=("Segoe UI", 9), text_color="#888888").pack()
    ctk.CTkLabel(stat_col1, text=str(account.get('sent_today', 0)), 
          font=("Segoe UI", 16, "bold"), 
          text_color="#00aaff").pack()
    
    # Success rate
    stat_col2 = ctk.CTkFrame(stats_row, fg_color="transparent")
    stat_col2.grid(row=0, column=1, sticky="ew", padx=10, pady=8)
    
    success_rate = account.get('success_rate', 100)
    
    ctk.CTkLabel(stat_col2, text="Success Rate", 
          font=("Segoe UI", 9), text_color="#888888").pack()
    ctk.CTkLabel(stat_col2, text=f"{success_rate}%", 
          font=("Segoe UI", 16, "bold"), 
          text_color="#00ff00").pack()
    
    # Risk level
    stat_col3 = ctk.CTkFrame(stats_row, fg_color="transparent")
    stat_col3.grid(row=0, column=2, sticky="ew", padx=10, pady=8)
    
    risk_score = account.get('risk_score', 0)
    
    if risk_score < 20:
      risk_text = "LOW"
      risk_color = "#00ff00"
    elif risk_score < 60:
      risk_text = "MED"
      risk_color = "#ffaa00"
    else:
      risk_text = "HIGH"
      risk_color = "#ff3333"
    
    ctk.CTkLabel(stat_col3, text="Risk Level", 
          font=("Segoe UI", 9), text_color="#888888").pack()
    ctk.CTkLabel(stat_col3, text=risk_text, 
          font=("Segoe UI", 16, "bold"), 
          text_color=risk_color).pack()
    
    # Last activity
    last_activity = account.get('last_activity', 'Never')
    ctk.CTkLabel(card, text=f"⏰ Last Activity: {last_activity}", 
          font=("Segoe UI", 9), text_color="#666666").pack(anchor="w", padx=15, pady=(0, 10))
  
  def add_account_dialog(self):
    """Show dialog to add new account"""
    dialog = ctk.CTkToplevel(self)
    dialog.title("Add New Account")
    dialog.geometry("450x550")
    dialog.transient(self)
    dialog.grab_set()
    
    # Center dialog
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
    y = (dialog.winfo_screenheight() // 2) - (550 // 2)
    dialog.geometry(f"450x550+{x}+{y}")
    
    apply_leadwave_theme(dialog)

    # Content
    content = ctk.CTkFrame(dialog, fg_color="transparent")
    content.pack(fill="both", expand=True, padx=20, pady=20)
    
    ctk.CTkLabel(content, text="Add New Account", font=heading(TYPOGRAPHY["h2"], "bold")).pack(pady=(0, 20))
    
    # Account Name
    ctk.CTkLabel(content, text="Account Name:", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(10, 5))
    name_entry = StyledInput(content, placeholder_text="e.g., Main Account, Backup 1")
    name_entry.pack(fill="x", pady=(0, 10))
    
    # Phone Number
    ctk.CTkLabel(content, text="Phone Number:", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(10, 5))
    phone_entry = StyledInput(content, placeholder_text="e.g., +8801712345678")
    phone_entry.pack(fill="x", pady=(0, 10))
    
    # Instance ID
    ctk.CTkLabel(content, text="Instance ID:", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(10, 5))
    instance_entry = StyledInput(content, placeholder_text="e.g., 1, 2, 3...")
    instance_entry.pack(fill="x", pady=(0, 10))
    
    # API Host (optional)
    ctk.CTkLabel(content, text="API Host (Optional):", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(10, 5))
    host_entry = StyledInput(content, placeholder_text="e.g., http://localhost:4000")
    host_entry.pack(fill="x", pady=(0, 10))
    host_entry.insert(0, SETTINGS.api_host)
    
    # Account Age
    ctk.CTkLabel(content, text="Account Age (days):", font=body(TYPOGRAPHY["body"], "bold")).pack(anchor="w", pady=(10, 5))
    age_entry = StyledInput(content, placeholder_text="e.g., 30")
    age_entry.pack(fill="x", pady=(0, 10))
    age_entry.insert(0, "30")
    
    # Priority checkbox
    priority_var = ctk.CTkCheckBox(content, text="⭐ Set as Priority Account")
    priority_var.pack(anchor="w", pady=10)
    
    # Buttons
    btn_frame = ctk.CTkFrame(content, fg_color="transparent")
    btn_frame.pack(fill="x", pady=(20, 0))
    
    def save_account():
      name = name_entry.get().strip()
      phone = phone_entry.get().strip()
      instance_id = instance_entry.get().strip()
      
      if not name or not phone or not instance_id:
        messagebox.showwarning("Warning", "Please fill all required fields!")
        return
      
      # Create account object
      account = {
        "name": name,
        "phone": phone,
        "instance_id": int(instance_id),
        "host": host_entry.get().strip() or SETTINGS.api_host,
        "account_age_days": int(age_entry.get().strip() or 30),
        "priority": priority_var.get(),
        "status": "offline",
        "health_score": 100,
        "sent_today": 0,
        "success_rate": 100,
        "risk_score": 0,
        "last_activity": "Never",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      }
      
      with self.accounts_lock:
        self.accounts.append(account)
      self.save_accounts()
      self.refresh_accounts()
      self.add_log(f" Added account: {name}", "success")
      
      dialog.destroy()
    
    PrimaryButton(btn_frame, text="Add Account", command=save_account).pack(side="left", fill="x", expand=True, padx=(0,5))
    
    cancel_btn = SecondaryButton(btn_frame, text="Cancel", command=dialog.destroy)
    cancel_btn.pack(side="left", fill="x", expand=True, padx=(5,0))
  
  def edit_account(self, account):
    """Edit account settings"""
    messagebox.showinfo("Edit Account", f"Editing: {account['name']}\n(Feature coming soon)")
  
  def toggle_account(self, account):
    """Toggle account active/paused"""
    with self.accounts_lock:
        if account['status'] == 'active':
          account['status'] = 'paused'
          self.add_log(f"⏸ Paused account: {account['name']}", "warning")
        else:
          account['status'] = 'active'
          self.add_log(f"▶ Activated account: {account['name']}", "success")
    
    self.refresh_accounts()
  
  def delete_account(self, account):
    """Delete account"""
    if messagebox.askyesno("Confirm Delete", 
               f"Delete account '{account['name']}'?\nThis cannot be undone."):
      with self.accounts_lock:
        self.accounts.remove(account)
      self.save_accounts()
      self.refresh_accounts()
      self.add_log(f" Deleted account: {account['name']}", "error")
  
  def activate_all(self):
    """Activate all accounts"""
    with self.accounts_lock:
        for account in self.accounts:
          if account['status'] != 'blocked':
            account['status'] = 'active'
    
    self.refresh_accounts()
    self.add_log("▶ All accounts activated", "success")
  
  def pause_all(self):
    """Pause all accounts"""
    with self.accounts_lock:
        for account in self.accounts:
          if account['status'] == 'active':
            account['status'] = 'paused'
    
    self.refresh_accounts()
    self.add_log("⏸ All accounts paused", "warning")
  
  def rebalance_load(self):
    """Rebalance account load based on current settings and simple health/risk rules."""
    with self.accounts_lock:
        if not self.accounts:
          messagebox.showinfo("Balancer", "No accounts configured to rebalance.")
          return

        # Optionally auto‑pause very risky active accounts.
        if self.auto_pause_risky.get():
          for account in self.accounts:
            if account.get("status") == "active" and account.get("risk_score", 0) >= 80:
              account["status"] = "paused"
              self.add_log(f" Auto-paused {account['name']} during rebalance (high risk)", "warning")

        # Optionally auto‑reactivate healthier, low‑risk accounts.
        if self.auto_reactivate.get():
          for account in self.accounts:
            if account.get("status") in {"paused", "offline"}:
              if account.get("risk_score", 0) < 40 and account.get("health_score", 0) >= 70:
                account["status"] = "active"

        # As a fallback, ensure at least one non‑blocked account is active.
        active_accounts = [a for a in self.accounts if a.get("status") == "active"]
        if not active_accounts:
          # Pick the healthiest, lowest‑risk non‑blocked account.
          candidates = [
            a for a in self.accounts
            if a.get("status") != "blocked"
          ]
          if candidates:
            best = max(
              candidates,
              key=lambda a: (
                a.get("health_score", 0),
                -a.get("risk_score", 0),
              ),
            )
            best["status"] = "active"
            self.add_log(f"▶ Activated {best['name']} as primary sender after rebalance", "success")

    self.refresh_accounts()
    self.add_log(" Rebalanced account load using current strategy", "info")

  def resync_now(self):
    """Reload accounts from disk and refresh the view."""
    try:
      self.accounts = self.load_accounts()
      self.refresh_accounts()
      self.add_log(" Manual resync from configuration file completed", "info")
    except Exception as e:
      messagebox.showerror("Error", f"Resync failed: {e}")

  def reset_all_stats(self):
    """Reset statistics for all accounts"""
    if messagebox.askyesno("Confirm Reset", "Reset all account statistics?"):
      for account in self.accounts:
        account['sent_today'] = 0
        account['health_score'] = 100
        account['success_rate'] = 100
        account['risk_score'] = 0
      
      self.refresh_accounts()
      self.add_log(" All statistics reset", "info")
  
  def update_stats(self):
    """Update overall statistics"""
    total = len(self.accounts)
    active = sum(1 for a in self.accounts if a["status"] == "active")
    blocked = sum(1 for a in self.accounts if a["status"] in ["blocked", "paused"])

    self.total_accounts_stat.set_value(str(total))
    self.active_accounts_stat.set_value(str(active))
    self.blocked_accounts_stat.set_value(str(blocked))

  def update_system_status_board(self):
    """Refresh the compact status board shown across management tabs."""
    total = len(self.accounts)
    active = sum(1 for a in self.accounts if a.get("status") == "active")

    # Aggregate simple health / risk hints from existing fields.
    if total:
      avg_health = sum(a.get("health_score", 0) for a in self.accounts) / total
    else:
      avg_health = 0
    high_risk = sum(1 for a in self.accounts if a.get("risk_score", 0) >= 60)

    # Queue length is not exposed directly; treat paused or blocked accounts as queued.
    queue_len = sum(
      1
      for a in self.accounts
      if a.get("status") in {"paused", "blocked", "offline"}
    )

    self.sys_accounts_stat.set_value(f"{active}/{total}")
    self.sys_health_stat.set_value(f"{avg_health:.0f}%")
    self.sys_risky_stat.set_value(str(high_risk))
    self.sys_queue_stat.set_value(str(queue_len))
  
  def start_monitoring(self):
    """Start background monitoring thread (idempotent)."""
    if self.monitoring_active:
      return
    self.monitoring_active = True
    start_daemon(self.monitoring_worker)
  
  def monitoring_worker(self):
    """Background worker to monitor accounts"""
    while self.monitoring_active and not self.stop_event.is_set():
      for account in self.accounts:
        if account["status"] == "active":
          # Real health check
          health = self.check_account_health(account)
          account["health_score"] = health
          account["last_activity"] = datetime.now().strftime("%H:%M")

          # Auto-pause if risky
          if self.auto_pause_risky.get() and account.get("risk_score", 0) > 80:
            account["status"] = "paused"
            self.add_log(f" Auto-paused {account['name']} (high risk)", "warning")

      # Refresh display every 30 seconds, but allow fast shutdown.
      if self.stop_event.wait(30):
        break
      if self.monitoring_active:
        ui_dispatch(self, self.refresh_accounts)

  def check_account_health(self, account):
    """Check actual account connection health"""
    try:
        acc_name = account.get('name')
        res = self.api.get_health(account=acc_name)
        if res.get('ok') and res.get('connected'):
            return 100
        return 0
    except:
        return 0
  
  def add_log(self, message, level="info"):
    """Add log entry"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    tag_map = {
      "info": "INFO",
      "success": "SUCCESS",
      "error": "ERROR",
      "warning": "WARN"
    }
    
    log_entry = f"[{timestamp}] {message}"
    self.log_box.insert("end", log_entry)
    self.log_box.see("end")
  
  def clear_log(self):
    """Clear activity log"""
    self.log_box.delete("1.0", "end")
  
  def get_next_account(self, strategy=None):
    """
    Get next account based on load balancing strategy
    """
    if not strategy:
      strategy = self.strategy_var.get()
    
    active_accounts = [a for a in self.accounts if a['status'] == 'active']
    
    if not active_accounts:
      return None
    
    if "Round Robin" in strategy:
      # Simple round robin
      return active_accounts[0] # Rotate after use
    
    elif "Least Used" in strategy:
      # Get account with least messages sent today
      return min(active_accounts, key=lambda a: a.get('sent_today', 0))
    
    elif "Health Based" in strategy:
      # Get account with best health score
      return max(active_accounts, key=lambda a: a.get('health_score', 0))
    
    elif "Random" in strategy:
      import random
      return random.choice(active_accounts)
    
    return active_accounts[0]

  def destroy(self):
    """Cleanup monitoring thread and API resources when the tab is destroyed."""
    self.monitoring_active = False
    if hasattr(self, "stop_event"):
      self.stop_event.set()
    try:
      self.api.close()
    except Exception:
      pass
    super().destroy()
