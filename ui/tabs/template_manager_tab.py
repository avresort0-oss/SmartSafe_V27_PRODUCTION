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
from core.engine.advanced_template_engine import AdvancedTemplateEngine

class TemplateManagerTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    self.templates_file = "templates.json"
    self.templates = self.load_templates()
    self.search_var = ctk.StringVar(value="")
    
    # Initialize Advanced Template Engine
    self.advanced_engine = AdvancedTemplateEngine()
    
    self.build_ui()
    # Use LeadWave theming so this manager matches the rest of the UI.
    apply_leadwave_theme(self)
    self.refresh_template_list()
  
  def build_ui(self):
    header = TabHeader(
      self,
      title="Template Manager PRO",
      subtitle="Create, preview, and reuse message templates",
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
    
    # Left panel - Template list
    left_card = SectionCard(main)
    left_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["xs"]))
    left_card.grid_rowconfigure(3, weight=1)  # Template list expands
    left_card.grid_columnconfigure(0, weight=1)
    
    # Template list header
    list_header = ctk.CTkFrame(left_card.inner_frame, fg_color="transparent")
    list_header.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(list_header, text="Saved Templates", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    self.template_count = ctk.CTkLabel(list_header, text="0", font=body(TYPOGRAPHY["body"], "bold"), text_color=COLORS["brand"])
    self.template_count.pack(side="right")
    
    # Category filter
    filter_frame = ctk.CTkFrame(left_card.inner_frame, fg_color="transparent")
    filter_frame.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(filter_frame, text="Filter:", font=body(TYPOGRAPHY["body"])).pack(side="left", padx=(0, 8))
    self.filter_var = ctk.StringVar(value="All")
    filter_menu = ctk.CTkOptionMenu(
      filter_frame,
      values=["All", "Favorites", "OTP", "Promo", "Follow-up", "Notification", "Custom"],
      variable=self.filter_var,
      command=lambda x: self.refresh_template_list(),
      fg_color=COLORS["surface_2"],
      button_color=COLORS["surface_3"],
      text_color=COLORS["text_primary"],
    )
    filter_menu.pack(side="left", fill="x", expand=True)
    
    # Search box
    search_frame = ctk.CTkFrame(left_card.inner_frame, fg_color="transparent")
    search_frame.pack(fill="x", pady=(0, SPACING["xs"]))
    ctk.CTkLabel(search_frame, text="Search", font=body(TYPOGRAPHY["body"])).pack(side="left", padx=(0, 8))
    self.search_entry = StyledInput(search_frame, placeholder_text="Search by name or text...")
    self.search_entry.pack(side="left", fill="x", expand=True)
    self.search_entry.bind("<KeyRelease>", self.on_search_change)
    
    # Template list
    self.template_list = ctk.CTkScrollableFrame(left_card.inner_frame, fg_color="transparent")
    self.template_list.pack(fill="both", expand=True)
    
    # Right panel - Editor
    right_card = SectionCard(main)
    right_card.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    
    # Editor header
    editor_header = ctk.CTkFrame(right_card.inner_frame, fg_color="transparent")
    editor_header.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(editor_header, text="Template Editor", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    SecondaryButton(editor_header, text="New Template", command=self.new_template, width=100).pack(side="right")
    
    # Name & Category Row
    meta_row = ctk.CTkFrame(right_card.inner_frame, fg_color="transparent")
    meta_row.pack(fill="x", pady=(0, SPACING["sm"]))
    meta_row.grid_columnconfigure(0, weight=2)
    meta_row.grid_columnconfigure(1, weight=1)
    
    # Name
    name_frame = ctk.CTkFrame(meta_row, fg_color="transparent")
    name_frame.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ctk.CTkLabel(name_frame, text="Template Name", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    self.name_entry = StyledInput(name_frame, placeholder_text="e.g., Welcome Message")
    self.name_entry.pack(fill="x")

    # Category
    cat_frame = ctk.CTkFrame(meta_row, fg_color="transparent")
    cat_frame.grid(row=0, column=1, sticky="ew")
    ctk.CTkLabel(cat_frame, text="Category", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    self.category_var = ctk.StringVar(value="Custom")
    category_menu = ctk.CTkOptionMenu(cat_frame, 
                     values=["OTP", "Promo", "Follow-up", "Notification", "Custom"],
                     variable=self.category_var,
                     fg_color=COLORS["surface_2"],
                     button_color=COLORS["surface_3"],
                     text_color=COLORS["text_primary"])
    category_menu.pack(fill="x")
    
    # Message section
    ctk.CTkLabel(right_card.inner_frame, text="Message Content", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    
    vars_frame = ctk.CTkFrame(right_card.inner_frame, fg_color="transparent")
    vars_frame.pack(fill="x", pady=(0, 4))
    ctk.CTkLabel(vars_frame, text="Variables: {name}, {phone}, {code}, {custom1}", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["info"]).pack(side="left")
    self.char_count = ctk.CTkLabel(vars_frame, text="0/1000", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.char_count.pack(side="right")
    
    self.message_box = StyledTextbox(right_card.inner_frame, height=150)
    self.message_box.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
    self.message_box.bind("<KeyRelease>", self.update_char_count)
    
    # Preview section
    ctk.CTkLabel(right_card.inner_frame, text="Live Preview", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    self.preview_box = StyledTextbox(right_card.inner_frame, height=60, fg_color=COLORS["surface_2"], text_color=COLORS["text_secondary"])
    self.preview_box.pack(fill="x", pady=(0, SPACING["sm"]))
    
    # Action buttons
    action_row = ctk.CTkFrame(right_card.inner_frame, fg_color="transparent")
    action_row.pack(fill="x")
    
    PrimaryButton(action_row, text="Save Template", command=self.save_template).pack(side="right", padx=(SPACING["xs"], 0))
    SecondaryButton(action_row, text="Update Preview", command=self.update_preview).pack(side="right", padx=(SPACING["xs"], 0))
    SecondaryButton(
      action_row,
      text="Delete",
      command=self.delete_template,
      fg_color=COLORS["danger"],
      hover_color=COLORS["danger_hover"],
      text_color=COLORS["text_inverse"],
    ).pack(side="left")
  
  def load_templates(self):
    if os.path.exists(self.templates_file):
      try:
        with open(self.templates_file, 'r', encoding='utf-8') as f:
          return json.load(f)
      except:
        return []
    return []
  
  def save_templates(self):
    with open(self.templates_file, 'w', encoding='utf-8') as f:
      json.dump(self.templates, f, indent=2, ensure_ascii=False)
  
  def refresh_template_list(self):
    # Clear existing
    for widget in self.template_list.winfo_children():
      widget.destroy()
    
    # Filter templates
    filter_cat = self.filter_var.get()
    base = self.templates
    if filter_cat == "Favorites":
      base = [t for t in self.templates if t.get('favorite', False)]
    elif filter_cat != "All":
      base = [t for t in self.templates if t.get('category') == filter_cat]
    
    query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
    if query:
      filtered = [
        t for t in base
        if query in str(t.get('name', '')).lower() or query in str(t.get('message', '')).lower()
      ]
    else:
      filtered = base
    
    # Update count
    self.template_count.configure(text=str(len(filtered)))
    
    if not filtered:
      ctk.CTkLabel(
        self.template_list,
        text="No templates found.\nCreate one to get started!",
        font=body(TYPOGRAPHY["body"]),
        text_color=COLORS["text_muted"],
      ).pack(pady=50)
      return
    
    # Create template cards
    for template in filtered:
      self.create_template_card(template)
  
  def create_template_card(self, template):
    card = ctk.CTkFrame(self.template_list, fg_color=COLORS["surface_2"], corner_radius=RADIUS["md"])
    card.pack(fill="x", pady=4, padx=4)
    
    # Header
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=10, pady=(10, 5))
    
    ctk.CTkLabel(
      header,
      text=template['name'],
      font=body(TYPOGRAPHY["body"], "bold"),
      text_color=COLORS["text_primary"],
    ).pack(side="left")
    
    # Favorite toggle
    fav_label = ctk.CTkLabel(
      header,
      text="★" if template.get('favorite', False) else "☆",
      font=body(TYPOGRAPHY["body"], "bold"),
      text_color=COLORS["warning"] if template.get('favorite', False) else COLORS["text_muted"],
      cursor="hand2",
    )
    fav_label.pack(side="right", padx=(4, 0))
    fav_label.bind("<Button-1>", lambda _e, t=template: self.toggle_favorite(t))
    
    # Category badge
    cat_colors = {
      "OTP": "#1a4d2e",
      "Promo": "#4d1a1a",
      "Follow-up": "#1a3a4d",
      "Notification": "#4d3a1a",
      "Custom": "#3a1a4d"
    }
    
    cat_color = cat_colors.get(template.get('category', 'Custom'), "#3a1a4d")
    
    cat_label = ctk.CTkLabel(
      header,
      text=template.get('category', 'Custom'),
      font=body(TYPOGRAPHY["caption"], "bold"),
      fg_color=cat_color,
      text_color=COLORS["text_inverse"],
      corner_radius=RADIUS["sm"],
      padx=8,
      pady=2,
    )
    cat_label.pack(side="right")
    
    # Preview
    preview_text = template['message'][:80] + "..." if len(template['message']) > 80 else template['message']
    
    ctk.CTkLabel(card, text=preview_text, 
          font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_secondary"],
          wraplength=280, justify="left").pack(anchor="w", padx=10, pady=5)
    
    # Load button
    SecondaryButton(card, text="Load Template", 
           command=lambda t=template: self.load_template(t), height=28).pack(fill="x", padx=10, pady=(5, 10))
  
  def load_template(self, template):
    self.name_entry.delete(0, "end")
    self.name_entry.insert(0, template['name'])
    
    self.category_var.set(template.get('category', 'Custom'))
    
    self.message_box.delete("1.0", "end")
    self.message_box.insert("1.0", template['message'])
    
    self.update_char_count()
    self.update_preview()
  
  def save_template(self):
    name = self.name_entry.get().strip()
    message = self.message_box.get("1.0", "end").strip()
    category = self.category_var.get()
    
    if not name or not message:
      messagebox.showwarning("Warning", "Name and message are required!")
      return
    
    # Check if template exists
    existing_index = None
    for i, t in enumerate(self.templates):
      if t['name'] == name:
        existing_index = i
        break
    
    template = {
      "name": name,
      "category": category,
      "message": message,
      "favorite": self._get_existing_favorite(name),
    }
    
    if existing_index is not None:
      # Update existing
      self.templates[existing_index] = template
      messagebox.showinfo("Success", "Template updated!")
    else:
      # Add new
      self.templates.append(template)
      messagebox.showinfo("Success", "Template saved!")
    
    self.save_templates()
    self.refresh_template_list()
  
  def delete_template(self):
    name = self.name_entry.get().strip()
    
    if not name:
      messagebox.showwarning("Warning", "Please load a template first!")
      return
    
    if messagebox.askyesno("Confirm Delete", f"Delete template '{name}'?"):
      self.templates = [t for t in self.templates if t['name'] != name]
      self.save_templates()
      self.refresh_template_list()
      self.new_template()
      messagebox.showinfo("Success", "Template deleted!")
  
  def new_template(self):
    self.name_entry.delete(0, "end")
    self.message_box.delete("1.0", "end")
    self.category_var.set("Custom")
    self.preview_box.delete("1.0", "end")
    self.update_char_count()
  
  def update_char_count(self, event=None):
    text = self.message_box.get("1.0", "end").strip()
    count = len(text)
    color = COLORS["success"] if count <= 1000 else COLORS["danger"]
    self.char_count.configure(text=f"{count}/1000", text_color=color)
  
  def update_preview(self):
    message = self.message_box.get("1.0", "end").strip()
    
    # Sample data
    preview = message.replace("{name}", "John Doe")
    preview = preview.replace("{phone}", "+8801712345678")
    preview = preview.replace("{code}", "123456")
    preview = preview.replace("{custom1}", "Sample1")
    preview = preview.replace("{custom2}", "Sample2")
    
    self.preview_box.delete("1.0", "end")
    self.preview_box.insert("1.0", preview)

  def on_search_change(self, event=None):
    """Update list when search text changes."""
    self.search_var.set(self.search_entry.get().strip())
    self.refresh_template_list()

  def _get_existing_favorite(self, name):
    """Preserve favorite flag when saving an existing template."""
    for t in self.templates:
      if t.get("name") == name:
        return t.get("favorite", False)
    return False

  def toggle_favorite(self, template):
    """Toggle favorite status for a template and refresh list."""
    name = template.get("name")
    if not name:
      return
    for t in self.templates:
      if t.get("name") == name:
        t["favorite"] = not t.get("favorite", False)
        break
    self.save_templates()
    self.refresh_template_list()
