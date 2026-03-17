import customtkinter as ctk
import json
import os
from tkinter import messagebox
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
    apply_leadwave_theme,
)

class AutoReplyTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    self.rules_file = "autoreply_rules.json"
    self.config_file = "autoreply_config.json"
    self.rules = self.load_rules()
    self.current_rule = None
    
    self.build_ui()
    # Match auto-reply visuals with the LeadWave tab styling.
    apply_leadwave_theme(self)
    self.refresh_rules_list()
    self.load_config()

  def build_ui(self):
    header = TabHeader(
      self,
      title="Auto-Reply PRO",
      subtitle="Keyword-based auto responses and rule editor",
    )
    header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

    # Status Badge
    self.status_badge = StatusBadge(header.actions, text="READY", tone="info")
    self.status_badge.pack(side="right")
    
    # Main container
    main = ctk.CTkFrame(self, fg_color="transparent")
    main.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
    main.grid_columnconfigure(0, weight=1) # List
    main.grid_columnconfigure(1, weight=2) # Editor
    main.grid_rowconfigure(0, weight=1)
    
    # Left panel - Rules list
    left_card = SectionCard(main)
    left_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
    left_card.grid_rowconfigure(1, weight=1)  # Rules list expands
    left_card.grid_columnconfigure(0, weight=1)
    
    list_header = ctk.CTkFrame(left_card.inner_frame, fg_color="transparent")
    list_header.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(list_header, text="Reply Rules", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    SecondaryButton(list_header, text="New Rule", command=self.new_rule, width=80).pack(side="right")
    
    self.rules_list_frame = ctk.CTkScrollableFrame(left_card.inner_frame, fg_color="transparent")
    self.rules_list_frame.pack(fill="both", expand=True)
    
    # Right panel - Editor
    right_col = ctk.CTkFrame(main, fg_color="transparent")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    
    # Global status
    status_card = SectionCard(right_col)
    status_card.pack(fill="x", pady=(0, SPACING["sm"]))
    status_header = ctk.CTkFrame(status_card.inner_frame, fg_color="transparent")
    status_header.pack(fill="x")
    ctk.CTkLabel(status_header, text="Auto-Reply Status", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    self.status_switch = ctk.CTkSwitch(status_header, text="Enabled", progress_color=COLORS["success"], command=self.save_config)
    self.status_switch.pack(side="right")
    self.status_switch.select()
    
    # Editor Card
    editor_card = SectionCard(right_col)
    editor_card.pack(fill="both", expand=True)
    
    ctk.CTkLabel(editor_card.inner_frame, text="Rule Editor", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    # Rule Name
    ctk.CTkLabel(editor_card.inner_frame, text="Rule Name", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    self.name_entry = StyledInput(editor_card.inner_frame, placeholder_text="e.g., Greeting, Price Inquiry")
    self.name_entry.pack(fill="x", pady=(0, SPACING["sm"]))
    
    # Keywords
    ctk.CTkLabel(editor_card.inner_frame, text="Keywords (comma-separated)", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    self.keywords_entry = StyledInput(editor_card.inner_frame, placeholder_text="hello, hi, price, info")
    self.keywords_entry.pack(fill="x", pady=(0, SPACING["sm"]))
    
    # Match Type
    ctk.CTkLabel(editor_card.inner_frame, text="Match Type", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    self.match_type_var = ctk.StringVar(value="Contains")
    match_type_seg = ctk.CTkSegmentedButton(editor_card.inner_frame, values=["Contains", "Exact"], variable=self.match_type_var)
    match_type_seg.pack(fill="x", pady=(0, SPACING["sm"]))
    
    # Reply Message
    ctk.CTkLabel(editor_card.inner_frame, text="Reply Message", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
    self.message_box = StyledTextbox(editor_card.inner_frame, height=120)
    self.message_box.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
    
    # Action Buttons
    action_row = ctk.CTkFrame(editor_card.inner_frame, fg_color="transparent")
    action_row.pack(fill="x")
    PrimaryButton(action_row, text="Save Rule", command=self.save_rule).pack(side="right", padx=(SPACING["xs"], 0))
    SecondaryButton(
      action_row,
      text="Delete",
      command=self.delete_rule,
      fg_color=COLORS["danger"],
      hover_color=COLORS["danger_hover"],
      text_color=COLORS["text_inverse"],
    ).pack(side="right")

  def load_rules(self):
    if os.path.exists(self.rules_file):
      try:
        with open(self.rules_file, 'r', encoding='utf-8') as f:
          return json.load(f)
      except:
        return []
    return []
    
  def load_config(self):
    if os.path.exists(self.config_file):
        try:
            with open(self.config_file, 'r') as f:
                cfg = json.load(f)
                if cfg.get("enabled", True):
                    self.status_switch.select()
                else:
                    self.status_switch.deselect()
        except:
            pass

  def save_config(self):
    with open(self.config_file, 'w') as f:
        json.dump({"enabled": self.status_switch.get() == 1}, f)

  def save_rules(self):
    with open(self.rules_file, 'w', encoding='utf-8') as f:
      json.dump(self.rules, f, indent=2)

  def refresh_rules_list(self):
    for widget in self.rules_list_frame.winfo_children():
      widget.destroy()
    
    if not self.rules:
      ctk.CTkLabel(self.rules_list_frame, text="No rules created yet.", font=body(TYPOGRAPHY["body"]), text_color=COLORS["text_muted"]).pack(pady=20)
      return
      
    for rule in self.rules:
      self.create_rule_card(rule)

  def create_rule_card(self, rule):
    is_active = self.current_rule and self.current_rule['name'] == rule['name']
    card_color = COLORS["surface_2"] if is_active else "transparent"
    
    card = ctk.CTkFrame(self.rules_list_frame, fg_color=card_color, corner_radius=RADIUS["md"], cursor="hand2")
    card.pack(fill="x", pady=4, padx=4)
    card.bind("<Button-1>", lambda e, r=rule: self.load_rule(r))
    
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=10, pady=10)
    
    name_label = ctk.CTkLabel(header, text=rule['name'], font=body(TYPOGRAPHY["body"], "bold"), text_color=COLORS["text_primary"])
    name_label.pack(side="left")
    name_label.bind("<Button-1>", lambda e, r=rule: self.load_rule(r))
    
    status_switch = ctk.CTkSwitch(header, text="", width=0, progress_color=COLORS["success"])
    status_switch.pack(side="right")
    if rule.get('enabled', True):
      status_switch.select()
    status_switch.configure(command=lambda r=rule: self.toggle_rule_status(r))

  def toggle_rule_status(self, rule):
    # Find the rule and update its status
    for r in self.rules:
        if r['name'] == rule['name']:
            r['enabled'] = not r.get('enabled', True)
            break
    self.save_rules()
    self.refresh_rules_list()

  def load_rule(self, rule):
    self.current_rule = rule
    self.name_entry.delete(0, "end")
    self.name_entry.insert(0, rule['name'])
    
    self.keywords_entry.delete(0, "end")
    self.keywords_entry.insert(0, ", ".join(rule.get('keywords', [])))
    
    self.match_type_var.set(rule.get('match_type', 'Contains'))
    
    self.message_box.delete("1.0", "end")
    self.message_box.insert("1.0", rule.get('message', ''))
    
    self.refresh_rules_list()

  def new_rule(self):
    self.current_rule = None
    self.name_entry.delete(0, "end")
    self.keywords_entry.delete(0, "end")
    self.message_box.delete("1.0", "end")
    self.match_type_var.set("Contains")
    self.refresh_rules_list()

  def save_rule(self):
    name = self.name_entry.get().strip()
    keywords = [k.strip() for k in self.keywords_entry.get().split(',') if k.strip()]
    message = self.message_box.get("1.0", "end").strip()
    
    if not name or not keywords or not message:
      messagebox.showwarning("Warning", "Rule Name, Keywords, and Message are required.")
      return
      
    new_rule_data = {
      "name": name,
      "keywords": keywords,
      "match_type": self.match_type_var.get(),
      "message": message,
      "enabled": True
    }
    
    # If it's an existing rule, update it
    if self.current_rule and self.current_rule['name'] == name:
      for i, r in enumerate(self.rules):
        if r['name'] == self.current_rule['name']:
          new_rule_data['enabled'] = r.get('enabled', True)
          self.rules[i] = new_rule_data
          break
    else: # It's a new rule or a renamed rule
      # Check if name already exists
      for r in self.rules:
          if r['name'] == name and (not self.current_rule or self.current_rule['name'] != name):
              messagebox.showerror("Error", f"A rule with the name '{name}' already exists.")
              return
      # If it was an existing rule that was renamed, remove the old one
      if self.current_rule:
          self.rules = [r for r in self.rules if r['name'] != self.current_rule['name']]
      self.rules.append(new_rule_data)
      
    self.current_rule = new_rule_data
    self.save_rules()
    self.refresh_rules_list()
    messagebox.showinfo("Success", "Rule saved! The auto-reply engine will pick up changes automatically.")

  def delete_rule(self):
    if not self.current_rule:
      messagebox.showwarning("Warning", "No rule selected to delete.")
      return
      
    if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the rule '{self.current_rule['name']}'?"):
      self.rules = [r for r in self.rules if r['name'] != self.current_rule['name']]
      self.save_rules()
      self.new_rule()
      self.refresh_rules_list()
      messagebox.showinfo("Success", "Rule deleted.")
