"""
SmartSafe V27 - Visual Flow Builder Tab
UI for creating and managing chatbot flows.
"""
import re
import json
import os
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import TabHeader, SectionCard, PrimaryButton, SecondaryButton, StyledTextbox, heading, SPACING, COLORS
from core.engine.flow_engine import FlowEngine
from core.ai.ai_service import AIService, get_ai_service
from ui.utils.threading_helpers import ui_dispatch

class FlowBuilderTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.flow_engine = FlowEngine()
        self.ai_service = get_ai_service()
        self.flows_dir = Path("flows")
        self.flows_dir.mkdir(exist_ok=True)
        self.current_flow_path: Path | None = None

        self.build_ui()
        self._configure_syntax_highlighting()
        self.refresh_flow_list()
        self.new_flow()

    def build_ui(self):
        header = TabHeader(
            self,
            title="Visual Flow Builder",
            subtitle="Create automated chatbot conversations with a drag-and-drop interface.",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=2)
        main_frame.grid_rowconfigure(0, weight=1)

        # --- Left Panel ---
        left_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # Flow Management
        mgmt_card = SectionCard(left_panel)
        mgmt_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(mgmt_card.inner_frame, text="Flow Management", font=heading(16)).pack(anchor="w")

        self.flow_list_frame = ctk.CTkScrollableFrame(mgmt_card.inner_frame, height=150)
        self.flow_list_frame.pack(fill="x", expand=True, pady=5)

        # Node Palette
        palette_card = SectionCard(left_panel)
        palette_card.pack(fill="x", pady=(0, SPACING["sm"]))
        ctk.CTkLabel(palette_card.inner_frame, text="Node Palette", font=heading(16)).pack(anchor="w")

        palette_grid = ctk.CTkFrame(palette_card.inner_frame, fg_color="transparent")
        palette_grid.pack(fill="x", pady=5)
        palette_grid.grid_columnconfigure((0, 1), weight=1)

        # Add buttons for each node type
        SecondaryButton(palette_grid, text="Send Message", height=28, command=lambda: self.insert_node_template("sendMessage")).grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)
        SecondaryButton(palette_grid, text="Get Input", height=28, command=lambda: self.insert_node_template("getUserInput")).grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)
        SecondaryButton(palette_grid, text="Condition", height=28, command=lambda: self.insert_node_template("condition")).grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=2)
        SecondaryButton(palette_grid, text="Wait", height=28, command=lambda: self.insert_node_template("wait")).grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=2)
        SecondaryButton(palette_grid, text="API Call", height=28, command=lambda: self.insert_node_template("apiCall")).grid(row=2, column=0, sticky="ew", padx=(0, 5), pady=2)
        SecondaryButton(palette_grid, text="Send Media", height=28, command=lambda: self.insert_node_template("sendMedia")).grid(row=2, column=1, sticky="ew", padx=(5, 0), pady=2)        
        SecondaryButton(palette_grid, text="Set Variable", height=28, command=lambda: self.insert_node_template("setVariable")).grid(row=3, column=0, sticky="ew", padx=(0, 5), pady=2)
        SecondaryButton(palette_grid, text="AI Condition", height=28, command=lambda: self.insert_node_template("aiCondition")).grid(row=3, column=1, sticky="ew", padx=(5, 0), pady=2)

        # JSON Editor
        editor_card = SectionCard(left_panel)
        editor_card.pack(fill="both", expand=True)
        ctk.CTkLabel(editor_card.inner_frame, text="Flow JSON Definition", font=heading(16)).pack(anchor="w", pady=(0, 5))
        self.json_editor = StyledTextbox(editor_card.inner_frame)
        self.json_editor.pack(fill="both", expand=True, pady=(0, 10))

        self.json_editor.bind("<KeyRelease>", self._on_text_change)

        # Editor button row
        editor_btn_row = ctk.CTkFrame(left_panel, fg_color="transparent")
        editor_btn_row.pack(fill="x", pady=(SPACING["sm"], 0))
        PrimaryButton(editor_btn_row, text="New Flow", command=self.new_flow).pack(side="left", expand=True, padx=(0, 5))
        PrimaryButton(editor_btn_row, text="Save Flow", command=self.save_flow).pack(side="left", expand=True, padx=(5, 0))

        # Prompt enhancement row
        enhance_row = ctk.CTkFrame(left_panel, fg_color="transparent")
        enhance_row.pack(fill="x", pady=(SPACING["sm"], 0))
        SecondaryButton(enhance_row, text="✨ Enhance Prompt", command=self._enhance_selected_prompt, height=32).pack(side="left", expand=True, fill="x")
        # --- Right Panel ---
        right_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        # Test Panel
        test_card = SectionCard(right_panel)
        test_card.pack(fill="both", expand=True)
        ctk.CTkLabel(test_card.inner_frame, text="Test Flow", font=heading(16)).pack(anchor="w")

        self.test_log = StyledTextbox(test_card.inner_frame)
        self.test_log.pack(fill="both", expand=True, pady=5)
        self.test_log.insert("end", "Bot responses will appear here.\n")
        self.test_log.configure(state="disabled")

        test_input_row = ctk.CTkFrame(test_card.inner_frame, fg_color="transparent")
        test_input_row.pack(fill="x", pady=5)

        self.test_input = ctk.CTkEntry(test_input_row, placeholder_text="Type your message to the bot...")
        self.test_input.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.test_input.bind("<Return>", self.send_test_message)

        PrimaryButton(test_input_row, text="Send", command=self.send_test_message).pack(side="left")

    def new_flow(self):
        self.current_flow_path = None
        self.json_editor.delete("1.0", "end")
        # Set default sample flow
        sample_flow = {
            "start_node_id": "welcome",
            "nodes": [
                {
                    "id": "welcome",
                    "type": "sendMessage",
                    "data": {"text": "Hello! What is your name?"},
                    "next_node_id": "get_name"
                },
                {
                    "id": "get_name",
                    "type": "getUserInput",
                    "data": {"variable": "user_name"},
                    "next_node_id": "call_api"
                },
                {
                    "id": "call_api",
                    "type": "apiCall",
                    "data": {
                        "url": "https://api.genderize.io/?name={user_name}",
                        "method": "GET",
                        "response_variable": "gender_data"
                    },
                    "next_node_id": "say_hello"
                },
                {
                    "id": "say_hello",
                    "type": "sendMessage",
                    "data": {"text": "Nice to meet you, {user_name}! I think you are {gender_data[gender]}."},
                    "next_node_id": "send_avatar"
                },
                {
                    "id": "send_avatar",
                    "type": "sendMedia",
                    "data": {
                        "url": "https://robohash.org/{user_name}.png",
                        "caption": "Here is your cool robot avatar!"
                    }
                }
            ]
        }
        self.json_editor.insert("1.0", json.dumps(sample_flow, indent=2))
        self.refresh_flow_list()

    def save_flow(self):
        raw_json = self.json_editor.get("1.0", "end").strip()
        if not raw_json:
            messagebox.showwarning("Warning", "Editor is empty.")
            return

        if not self.current_flow_path:
            dialog = ctk.CTkInputDialog(text="Enter flow name (e.g., support_flow):", title="Save New Flow")
            flow_name = dialog.get_input()
            if not flow_name:
                return
            self.current_flow_path = self.flows_dir / f"{flow_name}.json"

        try:
            # Validate JSON before saving
            json.loads(raw_json)
            with open(self.current_flow_path, "w", encoding="utf-8") as f:
                f.write(raw_json)
            
            self.refresh_flow_list()
            messagebox.showinfo("Success", f"Flow saved to {self.current_flow_path.name}")
        except Exception as e:
            messagebox.showerror("Error", f"JSON Error: {e}")

    def refresh_flow_list(self):
        for widget in self.flow_list_frame.winfo_children():
            widget.destroy()

        for flow_file in sorted(self.flows_dir.glob("*.json")):
            is_current = self.current_flow_path and self.current_flow_path.name == flow_file.name
            btn = ctk.CTkButton(
                self.flow_list_frame,
                text=flow_file.stem, # type: ignore
                fg_color= "green" if is_current else "transparent",
                command=lambda p=flow_file: self.load_flow_from_file(p)
            )
            btn.pack(fill="x", pady=2, padx=2)

    def load_flow_from_file(self, path: Path):
        self.current_flow_path = path
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.json_editor.delete("1.0", "end")
        self.json_editor.insert("1.0", content)
        self._highlight_syntax()
        self.refresh_flow_list()

    def send_test_message(self, event=None):
        user_message = self.test_input.get()
        if not user_message:
            return

        self.test_log.configure(state="normal")
        self.test_log.insert("end", f"You: {user_message}\n")
        self.test_log.configure(state="disabled")
        self.test_input.delete(0, "end")

        original_send_message = self.flow_engine.api.send_message

        def test_send_message(phone, message, **kwargs):
            def _update_test_log():
                self.test_log.configure(state="normal")
                self.test_log.insert("end", f"Bot: {message}\n")
                self.test_log.see("end")
                self.test_log.configure(state="disabled")
            ui_dispatch(self, _update_test_log)

        self.flow_engine.api.send_message = test_send_message

        raw_json = self.json_editor.get("1.0", "end").strip()
        flow_data = self.flow_engine.load_flow(raw_json)
        if flow_data:
            self.flow_engine.handle_incoming_message(phone="test_user_123", message=user_message, flow=flow_data)

        self.after(3000, lambda: setattr(self.flow_engine.api, 'send_message', original_send_message))

    def insert_node_template(self, node_type: str):
        templates = {
            "sendMessage": {
                "id": "new_message_node",
                "type": "sendMessage",
                "data": {"text": "Your message here."},
                "next_node_id": "next_node"
            },
            "getUserInput": {
                "id": "new_input_node",
                "type": "getUserInput",
                "data": {"variable": "user_response"},
                "next_node_id": "next_node"
            },
            "condition": {
                "id": "new_condition_node",
                "type": "condition",
                "data": {
                    "logic": "AND",
                    "rules": [
                        {"variable": "last_message", "operator": "contains", "value": "help"},
                        {"variable": "customer_status", "operator": "equals", "value": "premium"}
                    ]
                },
                "true_node_id": "if_true_node",
                "false_node_id": "if_false_node"
            },
            "wait": {
                "id": "new_wait_node",
                "type": "wait",
                "data": {"seconds": 5},
                "next_node_id": "next_node"
            },
            "apiCall": {
                "id": "new_api_call_node",
                "type": "apiCall",
                "data": {
                    "url": "https://api.example.com/data",
                    "method": "GET",
                    "headers": {"Authorization": "Bearer YOUR_TOKEN"},
                    "body": {},
                    "response_variable": "api_data"
                },
                "next_node_id": "next_node",
                "error_node_id": "error_handler_node"
            },
            "sendMedia": {
                "id": "new_media_node",
                "type": "sendMedia",
                "data": {
                    "url": "https://example.com/image.png",
                    "caption": "Here is an image for you!"
                },
                "next_node_id": "next_node"
            },
            "setVariable": {
                "id": "new_set_var_node",
                "type": "setVariable",
                "data": {
                    "variable": "custom_var_name",
                    "value": "custom_value"
                },
                "next_node_id": "next_node"
            },
            "aiCondition": {
                "id": "new_ai_condition_node",
                "type": "aiCondition",
                "data": {
                    "input_variable": "last_message",
                    "prompt": "Is the user asking for a human agent?"
                },
                "true_node_id": "transfer_to_agent_node",
                "false_node_id": "continue_flow_node"
            }
        }
        
        template = templates.get(node_type)
        if not template:
            return
            
        template_str = json.dumps(template, indent=4)
        
        try:
            self.json_editor.insert(ctk.INSERT, template_str + ",\n")
        except Exception:
            self.json_editor.insert(ctk.END, template_str + ",\n")
        
        self._highlight_syntax()

    def _configure_syntax_highlighting(self):
        self.json_editor.tag_config("key", foreground=COLORS["warning"])
        self.json_editor.tag_config("string", foreground=COLORS["success"])
        self.json_editor.tag_config("number", foreground=COLORS["info"])
        self.json_editor.tag_config("boolean", foreground=COLORS["brand"])
        self.json_editor.tag_config("null", foreground=COLORS["text_muted"])

    def _on_text_change(self, event=None):
        if hasattr(self, "_highlight_job"):
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(200, self._highlight_syntax)

    def _highlight_syntax(self):
        content = self.json_editor.get("1.0", "end-1c")
        
        for tag in ["key", "string", "number", "boolean", "null"]:
            self.json_editor.tag_remove(tag, "1.0", "end")

        for match in re.finditer(r'"([^"]*)"', content):
            start, end = f"1.0 + {match.start(0)}c", f"1.0 + {match.end(0)}c"
            self.json_editor.tag_add("string", start, end)

        for match in re.finditer(r'"([^"]+)"\s*:', content):
            start, end = f"1.0 + {match.start(0)}c", f"1.0 + {match.end(0)-1}c"
            self.json_editor.tag_remove("string", start, end)
            self.json_editor.tag_add("key", start, end)

        for match in re.finditer(r'\b(-?\d+(\.\d+)?)\b|\b(true|false|null)\b', content):
            start, end = f"1.0 + {match.start(0)}c", f"1.0 + {match.end(0)}c"
            value = match.group(0)
            tag = "boolean" if value in ["true", "false"] else "null" if value == "null" else "number"
            self.json_editor.tag_add(tag, start, end)

    def _enhance_selected_prompt(self):
        """Enhance the selected prompt text using AI"""
        try:
            # Get selected text or current line
            try:
                selected_text = self.json_editor.get("sel.first", "sel.last").strip()
            except Exception:
                # No selection, get current line
                cursor_pos = self.json_editor.index("insert")
                line_start = f"{cursor_pos.split('.')[0]}.0"
                line_end = f"{cursor_pos.split('.')[0]}.end"
                selected_text = self.json_editor.get(line_start, line_end).strip()
            
            if not selected_text:
                messagebox.showinfo("Info", "Please select or place cursor on a prompt to enhance.")
                return
            
            # Check if AI service is available
            if not self.ai_service.enabled:
                messagebox.showwarning("AI Unavailable", "AI service is not configured. Please set your API key in settings.")
                return
            
            # Show progress
            messagebox.showinfo("Enhancing", "AI is enhancing your prompt... Please wait.")
            
            # Get context - check if this is an AI Condition node
            context = None
            if "aiCondition" in selected_text or '"type"' in selected_text:
                context = "This is an AI Condition node prompt for flow logic"
            
            # Call AI to enhance the prompt
            enhanced = self.ai_service.enhance_prompt(selected_text, context)
            
            # Replace the selected text
            try:
                self.json_editor.delete("sel.first", "sel.last")
            except Exception:
                pass
            
            self.json_editor.insert("insert", enhanced)
            messagebox.showinfo("Success", "Prompt enhanced successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to enhance prompt: {str(e)}")