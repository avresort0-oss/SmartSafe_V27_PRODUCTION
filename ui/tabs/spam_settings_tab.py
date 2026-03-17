import customtkinter as ctk
from core.config import SETTINGS

class SpamSettingsTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        # Title
        title_label = ctk.CTkLabel(self, text="Spam Detection Settings", font=('Arial', 16, 'bold'))
        title_label.pack(pady=10)

        # Info label
        info_label = ctk.CTkLabel(self, text="These settings are read-only. Please configure them using environment variables.", wraplength=400)
        info_label.pack(pady=10)

        # Settings frame
        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill='x', padx=10, pady=5)

        # Enable spam detection
        enabled_label = ctk.CTkLabel(settings_frame, text=f"Spam Detection Enabled: {SETTINGS.spam_detection_enabled}")
        enabled_label.pack(anchor='w', padx=5, pady=2)

        # Threshold
        threshold_label = ctk.CTkLabel(settings_frame, text=f"Spam Threshold: {SETTINGS.spam_detection_threshold}")
        threshold_label.pack(anchor='w', padx=5, pady=2)

        # Auto block
        auto_block_label = ctk.CTkLabel(settings_frame, text=f"Auto-block Spam: {SETTINGS.spam_detection_auto_block}")
        auto_block_label.pack(anchor='w', padx=5, pady=2)

        # Patterns
        patterns_label = ctk.CTkLabel(settings_frame, text="Spam Patterns:")
        patterns_label.pack(anchor='w', padx=5, pady=2)

        patterns_textbox = ctk.CTkTextbox(settings_frame, height=100)
        patterns_textbox.pack(fill='x', padx=5, pady=2)
        patterns_textbox.insert("1.0", ", ".join(SETTINGS.spam_detection_patterns))
        patterns_textbox.configure(state="disabled")
