# ui/tabs/send_engine_tab.py - UPDATED with Advanced Interactive Buttons

import customtkinter as ctk
from tkinter import messagebox
import requests
import threading
from .dashboard_tab import DashboardTab  # assuming exists

class BaileysAPI:
    def __init__(self):
        self.base_url = "http://localhost:4000"

    def send_message(self, data):
        return requests.post(f"{self.base_url}/send", json=data).json()

class SendEngineTab(ctk.CTkScrollableFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.api = BaileysAPI()
        self._build_ui()
        self.apply_theme()

    def apply_theme(self):
        # Apply leadwave/neon theme
        self.configure(fg_color="transparent")

    def _build_ui(self):
        # Account selector
        account_frame = ctk.CTkFrame(self, fg_color="transparent")
        account_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(account_frame, text="Account:").pack(side="left")
        self.account_var = ctk.StringVar(value="default")
        self.account_dropdown = ctk.CTkOptionMenu(account_frame, variable=self.account_var, values=["default", "account1", "account2"])
        self.account_dropdown.pack(side="right", padx=10)

        # Number entry
        number_frame = ctk.CTkFrame(self, fg_color="transparent")
        number_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(number_frame, text="Number:").pack(side="left")
        self.number_entry = ctk.CTkEntry(number_frame, placeholder_text="88017xxxxxxxx")
        self.number_entry.pack(side="right", padx=10, fill="x", expand=True)

        # Message
        message_frame = ctk.CTkFrame(self, fg_color="transparent")
        message_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(message_frame, text="Message:").pack(anchor="w")
        self.message_entry = ctk.CTkTextbox(message_frame, height=60)
        self.message_entry.pack(fill="x", pady=5)

        # Advanced buttons frame
        advanced_frame = ctk.CTkFrame(self, fg_color="transparent")
        advanced_frame.pack(fill="x", pady=10)

        self.btn_send = ctk.CTkButton(advanced_frame, text="Send Message", command=self.send_message_thread, fg_color="green", hover_color="darkgreen")
        self.btn_send.pack(side="left", padx=5)

        self.btn_reaction = ctk.CTkButton(advanced_frame, text="Reaction 🔥", command=self.send_reaction_thread, fg_color="purple")
        self.btn_reaction.pack(side="left", padx=5)

        self.btn_poll = ctk.CTkButton(advanced_frame, text="Poll 📊", command=self.send_poll_thread, fg_color="blue")
        self.btn_poll.pack(side="left", padx=5)

        self.btn_location = ctk.CTkButton(advanced_frame, text="Location 📍", command=self.send_location_thread, fg_color="green")
        self.btn_location.pack(side="left", padx=5)

        self.btn_story = ctk.CTkButton(advanced_frame, text="Story 📖", command=self.send_story_thread, fg_color="orange")
        self.btn_story.pack(side="left", padx=5)

        self.btn_buttons = ctk.CTkButton(advanced_frame, text="Buttons", command=self.send_buttons_thread, fg_color="#FF6B6B")
        self.btn_buttons.pack(side="left", padx=5)

        self.status_label = ctk.CTkLabel(self, text="Ready", text_color="green")
        self.status_label.pack(pady=10)

    def send_message_thread(self):
        threading.Thread(target=self.send_message, daemon=True).start()

    def send_message(self):
        data = {
            "number": self.number_entry.get(),
            "message": self.message_entry.get("1.0", "end-1c"),
            "account": self.account_var.get()
        }
        try:
            response = self.api.send_message(data)
            self.status_label.configure(text=f"Queued: {response.get('jobId', 'N/A')}", text_color="green")
        except Exception as e:
            self.status_label.configure(text=f"Error: {str(e)}", text_color="red")

    def send_reaction_thread(self):
        threading.Thread(target=self.send_reaction, daemon=True).start()

    def send_reaction(self):
        data = {
            "number": self.number_entry.get(),
            "reaction": {"emoji": "🔥", "originalMessageId": "msg123"},
            "account": self.account_var.get()
        }
        response = requests.post("http://localhost:4000/send", json=data).json()
        self.status_label.configure(text=f"Reaction Queued: {response.get('jobId')}", text_color="purple")

    def send_poll_thread(self):
        threading.Thread(target=self.send_poll, daemon=True).start()

    def send_poll(self):
        data = {
            "number": self.number_entry.get(),
            "poll": {"name": "Vote Now", "options": ["Yes", "No"], "selectableCount": 1},
            "account": self.account_var.get()
        }
        response = self.api.send_message(data)
        self.status_label.configure(text="Poll queued!", text_color="blue")

    def send_location_thread(self):
        threading.Thread(target=self.send_location, daemon=True).start()

    def send_location(self):
        data = {
            "number": self.number_entry.get(),
            "location": {"lat": 23.8103, "lng": 90.4125, "name": "Dhaka"},
            "account": self.account_var.get()
        }
        response = self.api.send_message(data)
        self.status_label.configure(text="Location queued!", text_color="green")

    def send_story_thread(self):
        threading.Thread(target=self.send_story, daemon=True).start()

    def send_story(self):
        data = {
            "number": self.number_entry.get(),
            "story": true,
            "message": self.message_entry.get("1.0", "end-1c"),
            "account": self.account_var.get()
        }
        response = self.api.send_message(data)
        self.status_label.configure(text="Story queued!", text_color="orange")

    def send_buttons_thread(self):
        threading.Thread(target=self.send_buttons, daemon=True).start()

    def send_buttons(self):
        data = {
            "number": self.number_entry.get(),
            "message": self.message_entry.get("1.0", "end-1c"),
            "buttons": [{"text": "Yes"}, {"text": "No"}, {"text": "Later"}],
            "account": self.account_var.get()
        }
        response = self.api.send_message(data)
        self.status_label.configure(text="Buttons queued!", text_color="#FF6B6B")

