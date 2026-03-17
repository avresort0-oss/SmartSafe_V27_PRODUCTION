import customtkinter as ctk
import csv
import os
from tkinter import filedialog, messagebox
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

class BulkFormatterTab(ctk.CTkFrame):
  def __init__(self, master):
    super().__init__(master, fg_color="transparent")
    self.contacts = []
    self.cleaned_contacts = []
    self.invalid_count = 0
    self.duplicate_count = 0
    
    self.build_ui()
    # Apply LeadWave theming so formatter cards match other PRO tabs.
    apply_leadwave_theme(self)
  
  def build_ui(self):
    header = TabHeader(
      self,
      title="Bulk Formatter PRO",
      subtitle="Clean, validate, and export contact lists",
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
    left_col.grid_rowconfigure(1, weight=1)  # Preview card expands
    left_col.grid_columnconfigure(0, weight=1)
    
    # Input & Options Card
    input_card = SectionCard(left_col)
    input_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(input_card.inner_frame, text="Input & Options", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    # Upload Row
    upload_row = ctk.CTkFrame(input_card.inner_frame, fg_color="transparent")
    upload_row.pack(fill="x", pady=(0, SPACING["xs"]))
    SecondaryButton(upload_row, text="Upload File", command=self.upload_file).pack(side="left", fill="x", expand=True, padx=(0, SPACING["xxs"]))
    PrimaryButton(upload_row, text="Process & Clean", command=self.process_file).pack(side="left", fill="x", expand=True, padx=(SPACING["xxs"], 0))
    
    self.file_info = ctk.CTkLabel(input_card.inner_frame, text="No file selected", font=body(TYPOGRAPHY["caption"]), text_color=COLORS["text_muted"])
    self.file_info.pack(anchor="w", pady=(0, SPACING["sm"]))
    
    # Options
    ctk.CTkLabel(input_card.inner_frame, text="Processing Rules", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, SPACING["xxs"]))
    self.opt_format = ctk.CTkCheckBox(input_card.inner_frame, text="Auto-format numbers (+880)")
    self.opt_format.pack(anchor="w", pady=4)
    self.opt_format.select()
    
    self.opt_duplicates = ctk.CTkCheckBox(input_card.inner_frame, text="Remove duplicates")
    self.opt_duplicates.pack(anchor="w", pady=4)
    self.opt_duplicates.select()
    
    self.opt_invalid = ctk.CTkCheckBox(input_card.inner_frame, text="Remove invalid numbers")
    self.opt_invalid.pack(anchor="w", pady=4)
    self.opt_invalid.select()
    
    self.opt_clean = ctk.CTkCheckBox(input_card.inner_frame, text="Clean formatting (spaces, dashes)")
    self.opt_clean.pack(anchor="w", pady=4)
    self.opt_clean.select()

    # Split Utility Card
    split_card = SectionCard(left_col)
    split_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(split_card.inner_frame, text="Split Utility", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    split_row = ctk.CTkFrame(split_card.inner_frame, fg_color="transparent")
    split_row.pack(fill="x")
    
    ctk.CTkLabel(split_row, text="Rows per file:", font=body(TYPOGRAPHY["body"])).pack(side="left", padx=(0, 8))
    self.split_count = StyledInput(split_row, width=100, placeholder_text="1000")
    self.split_count.pack(side="left", padx=(0, 8))
    self.split_count.insert(0, "1000")
    
    SecondaryButton(split_row, text="Split File", command=self.split_file).pack(side="left", fill="x", expand=True)

    # Original Preview Card
    preview_card = SectionCard(left_col)
    preview_card.pack(fill="both", expand=True)
    ctk.CTkLabel(preview_card.inner_frame, text="Original Preview", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xs"]))
    
    self.original_preview = StyledTextbox(preview_card.inner_frame)
    self.original_preview.pack(fill="both", expand=True)

    # Right panel
    right_col = ctk.CTkFrame(main, fg_color="transparent")
    right_col.grid(row=0, column=1, sticky="nsew", padx=(SPACING["xs"], 0))
    right_col.grid_rowconfigure(2, weight=1) # Results expand

    # Step indicator
    step_card = SectionCard(right_col)
    step_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(step_card.inner_frame, text="Formatter Flow", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["xs"]))
    self.step_label = ctk.CTkLabel(
      step_card.inner_frame,
      text="Step 1 of 3 — Input file",
      font=body(TYPOGRAPHY["body"], "bold"),
      text_color=COLORS["info"],
    )
    self.step_label.pack(anchor="w", pady=(0, SPACING["xxs"]))
    self.step_progress = ctk.CTkProgressBar(step_card.inner_frame, height=10)
    self.step_progress.pack(fill="x")
    self.step_progress.set(1 / 3)
    
    # Stats Card
    stats_card = SectionCard(right_col)
    stats_card.pack(fill="x", pady=(0, SPACING["sm"]))
    ctk.CTkLabel(stats_card.inner_frame, text="Statistics", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
    
    stats_grid = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
    stats_grid.pack(fill="x")
    stats_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)
    
    self.stat_total = StatCard(stats_grid, "Total", "0", "info")
    self.stat_total.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xxs"]))
    
    self.stat_valid = StatCard(stats_grid, "Valid", "0", "success")
    self.stat_valid.grid(row=0, column=1, sticky="ew", padx=SPACING["xxs"])
    
    self.stat_invalid = StatCard(stats_grid, "Invalid", "0", "warning")
    self.stat_invalid.grid(row=0, column=2, sticky="ew", padx=SPACING["xxs"])
    
    self.stat_removed = StatCard(stats_grid, "Duplicates", "0", "danger")
    self.stat_removed.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    # Cleaned Results Card
    results_card = SectionCard(right_col)
    results_card.pack(fill="both", expand=True)
    
    res_header = ctk.CTkFrame(results_card.inner_frame, fg_color="transparent")
    res_header.pack(fill="x", pady=(0, SPACING["xs"]))
    ctk.CTkLabel(res_header, text="Cleaned Results", font=heading(TYPOGRAPHY["h3"], "bold")).pack(side="left")
    SecondaryButton(res_header, text="Export CSV", command=self.export_csv, width=100, height=28).pack(side="right")
    
    self.cleaned_preview = StyledTextbox(results_card.inner_frame)
    self.cleaned_preview.pack(fill="both", expand=True)
  
  def upload_file(self):
    """Upload CSV or Excel file"""
    file_path = filedialog.askopenfilename(
      title="Select File",
      filetypes=[("CSV Files", "*.csv"), ("Excel Files", "*.xlsx"), ("All Files", "*.*")]
    )
    
    if not file_path:
      return
    
    try:
      self.contacts = []
      
      if file_path.endswith('.csv'):
        with open(file_path, 'r', encoding='utf-8') as f:
          reader = csv.DictReader(f)
          for row in reader:
            self.contacts.append(row)
      else:
        messagebox.showinfo("Info", "Excel support coming soon! Use CSV for now.")
        return
      
      self.file_info.configure(text=f"Loaded: {len(self.contacts)} contacts")
      self.stat_total.set_value(str(len(self.contacts)))
      self._set_step(1)
      self.update_original_preview()
      
    except Exception as e:
      messagebox.showerror("Error", f"Failed to load file: {str(e)}")
  
  def update_original_preview(self):
    """Update original data preview"""
    self.original_preview.delete("1.0", "end")
    
    preview_text = "Original Numbers:\n" + "="*40 + "\n"
    
    for i, contact in enumerate(self.contacts[:20], 1):
      phone = contact.get('phone', contact.get('number', 'N/A'))
      name = contact.get('name', 'N/A')
      preview_text += f"{i}. {phone} - {name}\n"
    
    if len(self.contacts) > 20:
      preview_text += f"\n... and {len(self.contacts) - 20} more"
    
    self.original_preview.insert("1.0", preview_text)
  
  def process_file(self):
    """Process and clean contacts"""
    if not self.contacts:
      messagebox.showwarning("Warning", "Please upload a file first!")
      return
    
    self.cleaned_contacts = []
    duplicates = set()
    self.invalid_count = 0
    self.duplicate_count = 0
    
    for contact in self.contacts:
      phone = contact.get('phone', contact.get('number', '')).strip()
      
      # Clean formatting
      if self.opt_clean.get():
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        phone = ''.join(filter(str.isdigit, phone))
      
      # Format number
      if self.opt_format.get():
        # Add country code if missing
        if len(phone) == 11 and phone.startswith('0'):
          phone = '880' + phone[1:]
        elif len(phone) == 10:
          phone = '880' + phone
      
      # Validate
      if self.opt_invalid.get():
        if len(phone) < 11 or len(phone) > 15:
          self.invalid_count += 1
          continue
      
      # Remove duplicates
      if self.opt_duplicates.get():
        if phone in duplicates:
          self.duplicate_count += 1
          continue
        duplicates.add(phone)
      
      # Add to cleaned list
      contact['phone'] = phone
      self.cleaned_contacts.append(contact)
    
    # Update stats
    self.stat_valid.set_value(str(len(self.cleaned_contacts)))
    self.stat_invalid.set_value(str(self.invalid_count))
    self.stat_removed.set_value(str(self.duplicate_count))
    
    # Update preview
    self.update_cleaned_preview()
    self._set_step(2)
    
    messagebox.showinfo(
      "Success",
      "Processing complete!\n\n"
      f"Valid: {len(self.cleaned_contacts)}\n"
      f"Invalid removed: {self.invalid_count}\n"
      f"Duplicates removed: {self.duplicate_count}",
    )
  
  def update_cleaned_preview(self):
    """Update cleaned data preview"""
    self.cleaned_preview.delete("1.0", "end")
    
    preview_text = "Cleaned Numbers:\n" + "="*40 + "\n"
    
    for i, contact in enumerate(self.cleaned_contacts[:20], 1):
      phone = contact.get('phone', 'N/A')
      name = contact.get('name', 'N/A')
      preview_text += f"{i}. {phone} - {name}\n"
    
    if len(self.cleaned_contacts) > 20:
      preview_text += f"\n... and {len(self.cleaned_contacts) - 20} more"
    
    self.cleaned_preview.insert("1.0", preview_text)
  
  def export_csv(self):
    """Export cleaned contacts to CSV"""
    if not self.cleaned_contacts:
      messagebox.showwarning("Warning", "Please process the file first!")
      return
    
    file_path = filedialog.asksaveasfilename(
      defaultextension=".csv",
      filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    
    if not file_path:
      return
    
    try:
      with open(file_path, 'w', newline='', encoding='utf-8') as f:
        if self.cleaned_contacts:
          fieldnames = self.cleaned_contacts[0].keys()
          writer = csv.DictWriter(f, fieldnames=fieldnames)
          writer.writeheader()
          writer.writerows(self.cleaned_contacts)
      
      self._set_step(3)
      messagebox.showinfo("Success", f"Exported {len(self.cleaned_contacts)} contacts successfully!")
      
    except Exception as e:
      messagebox.showerror("Error", f"Failed to export: {str(e)}")

  def split_file(self):
    """Split loaded contacts into multiple files"""
    if not self.contacts:
      messagebox.showwarning("Warning", "Please upload a file first!")
      return
      
    try:
      chunk_size = int(self.split_count.get())
      if chunk_size <= 0:
        raise ValueError
    except ValueError:
      messagebox.showerror("Error", "Invalid row count")
      return
      
    save_dir = filedialog.askdirectory(title="Select Output Directory")
    if not save_dir:
      return
      
    try:
      total = len(self.contacts)
      chunks = [self.contacts[i:i + chunk_size] for i in range(0, total, chunk_size)]
      
      for i, chunk in enumerate(chunks):
        filepath = os.path.join(save_dir, f"split_part_{i+1}.csv")
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if chunk:
                fieldnames = chunk[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(chunk)
                
      messagebox.showinfo("Success", f"Split into {len(chunks)} files successfully!")
      
    except Exception as e:
      messagebox.showerror("Error", f"Failed to split file: {str(e)}")

  def _set_step(self, step_index):
    """Update step progress label and bar (1-3)."""
    step_index = max(1, min(3, int(step_index)))
    labels = {
      1: "Step 1 of 3 — Input file",
      2: "Step 2 of 3 — Clean & validate",
      3: "Step 3 of 3 — Export cleaned list",
    }
    self.step_label.configure(text=labels.get(step_index, ""))
    self.step_progress.set(step_index / 3)
