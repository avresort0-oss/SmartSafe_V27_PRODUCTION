import customtkinter as ctk
import json
import os
from tkinter import messagebox
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    TabHeader,
    StatusBadge,
    heading,
    body,
    SectionCard,
    PrimaryButton,
    SecondaryButton,
    StyledInput,
    apply_leadwave_theme,
)

class SettingsTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.settings_file = "settings.json"
        self.settings = self.load_settings()
        self.build_ui()
        # Align visual style with the premium LeadWave dashboard.
        apply_leadwave_theme(self)

    def load_settings(self):
        defaults = {
            "api_host": "http://localhost:4000",
            "api_key": "",
            "default_risk_mode": "SAFE",
            "performance_profile": "Safe",
            "logging_level": "INFO",
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    defaults.update(data) # type: ignore
            except:
                pass
        return defaults

    def build_ui(self):
        header = TabHeader(
            self,
            title="System Settings",
            subtitle="API, performance, and maintenance preferences",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"])) # type: ignore

        # Status Badge
        self.status_badge = StatusBadge(header.actions, text="OK", tone="success")
        self.status_badge.pack(side="right")

        # Content Scrollable Container
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
        
        # API Config
        api_card = SectionCard(content)
        api_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(api_card.inner_frame, text="API Configuration", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        ctk.CTkLabel(api_card.inner_frame, text="API Host URL", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
        self.api_host_entry = StyledInput(api_card.inner_frame, placeholder_text="http://localhost:4000")
        self.api_host_entry.pack(fill="x", pady=(0, SPACING["sm"]))
        self.api_host_entry.insert(0, self.settings["api_host"])
        
        ctk.CTkLabel(api_card.inner_frame, text="API Key (Optional)", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
        self.api_key_entry = StyledInput(api_card.inner_frame, placeholder_text="Secret Key")
        self.api_key_entry.pack(fill="x", pady=(0, SPACING["sm"]))
        self.api_key_entry.insert(0, self.settings["api_key"])

        # Preferences
        pref_card = SectionCard(content)
        pref_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(pref_card.inner_frame, text="System Preferences", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        ctk.CTkLabel(pref_card.inner_frame, text="Default Risk Mode", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(0, 4))
        self.risk_mode_var = ctk.StringVar(value=self.settings["default_risk_mode"])
        ctk.CTkSegmentedButton(pref_card.inner_frame, values=["SAFE", "FAST", "TURBO"], variable=self.risk_mode_var).pack(fill="x", pady=(0, SPACING["sm"]))
        
        ctk.CTkLabel(pref_card.inner_frame, text="Performance Profile", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(8, 4))
        self.performance_profile_var = ctk.StringVar(value=self.settings.get("performance_profile", "Safe"))
        ctk.CTkSegmentedButton(
            pref_card.inner_frame,
            values=["Safe", "Balanced", "Aggressive"],
            variable=self.performance_profile_var,
        ).pack(fill="x", pady=(0, SPACING["sm"]))
        
        ctk.CTkLabel(pref_card.inner_frame, text="Logging Level", font=body(TYPOGRAPHY["caption"], "bold")).pack(anchor="w", pady=(8, 4))
        self.logging_level_var = ctk.StringVar(value=self.settings.get("logging_level", "INFO"))
        ctk.CTkSegmentedButton(
            pref_card.inner_frame,
            values=["ERROR", "WARN", "INFO", "DEBUG"],
            variable=self.logging_level_var,
        ).pack(fill="x", pady=(0, SPACING["sm"]))

        # Maintenance
        maintenance_card = SectionCard(content)
        maintenance_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(maintenance_card.inner_frame, text="Maintenance", font=heading(TYPOGRAPHY["h3"], "bold")).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        SecondaryButton(
            maintenance_card.inner_frame,
            text="Clear Application Logs",
            command=self.clear_logs,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color=COLORS["text_inverse"],
        ).pack(anchor="w")

        # Save Button
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))
        PrimaryButton(save_frame, text="Save Settings", command=self.save_settings).pack(side="right")

    def save_settings(self):
        self.settings["api_host"] = self.api_host_entry.get().strip()
        self.settings["api_key"] = self.api_key_entry.get().strip()
        self.settings["default_risk_mode"] = self.risk_mode_var.get()
        self.settings["performance_profile"] = self.performance_profile_var.get()
        self.settings["logging_level"] = self.logging_level_var.get()
        
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            
            messagebox.showinfo("Success", "Settings saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def clear_logs(self):
        if messagebox.askyesno("Confirm", "Are you sure you want to delete all log files?"):
            try:
                log_dir = "logs"
                if os.path.exists(log_dir):
                    for f in os.listdir(log_dir):
                        file_path = os.path.join(log_dir, f)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                messagebox.showinfo("Success", "Logs cleared.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear logs: {e}")
