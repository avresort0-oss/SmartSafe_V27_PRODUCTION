"""
SmartSafe V27 - ML Analytics Tab
ML-powered risk analysis and insights dashboard
"""

import customtkinter as ctk
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from ui.theme.design_tokens import COLORS, TYPOGRAPHY, SPACING
from ui.theme.leadwave_components import (
    SectionCard,
    StatCard,
    TitleLabel,
    CaptionLabel,
    TabHeader,
    StatusBadge,
)
from core.engine.risk_brain import RiskBrain, RiskLevel, RiskMode
from core.engine.ml_risk_engine import MLRiskEngine
from core.engine.engine_service import get_engine_service
from ui.utils.threading_helpers import start_daemon, ui_dispatch

FONT_FAMILY = TYPOGRAPHY.get("font_family", "Inter")


class MLAnalyticsTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        # Services
        self.engine_service = get_engine_service()
        self.risk_brain = RiskBrain()
        self.ml_engine = MLRiskEngine()

        # UI State
        self.stop_event = threading.Event()
        self.current_profile = ctk.StringVar(value="SAFE")

        # Header
        header = TabHeader(
            self,
            title="ML Risk Analytics",
            subtitle="AI-powered risk analysis and predictions",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Status Badge
        self.status_badge = StatusBadge(header.actions, text="ACTIVE", tone="success", pulse=True)
        self.status_badge.pack(side="right")

        # Main Content
        self._build_content()

        # Start background update
        start_daemon(self._update_loop)

    def _build_content(self):
        """Build main content area"""
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))
        
        # Left Panel - Risk Metrics
        left_panel = ctk.CTkFrame(content, fg_color="transparent")
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, SPACING["xs"]))
        
        # Right Panel - ML Insights
        right_panel = ctk.CTkFrame(content, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True, padx=(SPACING["xs"], 0))
        
        self._build_risk_metrics_panel(left_panel)
        self._build_ml_insights_panel(right_panel)
        self._build_risk_factors_panel(left_panel)
        self._build_recommendations_panel(right_panel)

    def _build_risk_metrics_panel(self, parent):
        """Build risk metrics panel"""
        card = SectionCard(parent)
        card.pack(fill="x", pady=(0, SPACING["md"]))

        TitleLabel(card.inner_frame, text="Risk Metrics").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Stats Grid
        stats_grid = ctk.CTkFrame(card.inner_frame, fg_color="transparent")
        stats_grid.pack(fill="x", pady=(0, SPACING["sm"]))
        
        for i in range(3):
            stats_grid.grid_columnconfigure(i, weight=1)

        # Create stat cards
        self.risk_score_card = self._create_stat_card(stats_grid, 0, 0, "Risk Score", "0", COLORS["brand"])
        self.hourly_usage_card = self._create_stat_card(stats_grid, 1, 0, "Hourly Usage", "0/0", COLORS["warning"])
        self.daily_usage_card = self._create_stat_card(stats_grid, 2, 0, "Daily Usage", "0/0", COLORS["info"])
        
        self.delay_card = self._create_stat_card(stats_grid, 0, 1, "Avg Delay", "0s", COLORS["text_secondary"])
        self.messages_card = self._create_stat_card(stats_grid, 1, 1, "Messages Sent", "0", COLORS["success"])
        self.pauses_card = self._create_stat_card(stats_grid, 2, 1, "Total Pauses", "0", COLORS["danger"])

    def _build_ml_insights_panel(self, parent):
        """Build ML insights panel"""
        card = SectionCard(parent)
        card.pack(fill="x", pady=(0, SPACING["md"]))

        TitleLabel(card.inner_frame, text="ML Insights").pack(anchor="w", pady=(0, SPACING["sm"]))

        # ML Prediction
        ml_frame = ctk.CTkFrame(card.inner_frame, fg_color="transparent")
        ml_frame.pack(fill="x", pady=(0, SPACING["sm"]))
        
        CaptionLabel(ml_frame, text="ML Risk Prediction").pack(anchor="w")
        self.ml_prediction_text = ctk.CTkTextbox(
            ml_frame,
            height=60,
            font=(FONT_FAMILY, 12)
        )
        self.ml_prediction_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.ml_prediction_text.configure(state="disabled")

        # Confidence
        conf_frame = ctk.CTkFrame(card.inner_frame, fg_color="transparent")
        conf_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(conf_frame, text="ML Confidence").pack(anchor="w")
        self.ml_confidence_text = ctk.CTkTextbox(
            conf_frame,
            height=40,
            font=(FONT_FAMILY, 12)
        )
        self.ml_confidence_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.ml_confidence_text.configure(state="disabled")

    def _build_risk_factors_panel(self, parent):
        """Build risk factors panel"""
        card = SectionCard(parent)
        card.pack(fill="both", expand=True)

        TitleLabel(card.inner_frame, text="Risk Factors").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Factors list
        self.factors_text = ctk.CTkTextbox(
            card.inner_frame,
            height=150,
            font=(FONT_FAMILY, 12)
        )
        self.factors_text.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
        self.factors_text.configure(state="disabled")

        # Profile Selector
        profile_frame = ctk.CTkFrame(card.inner_frame, fg_color="transparent")
        profile_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(profile_frame, text="Risk Profile").pack(side="left", padx=(0, SPACING["xs"]))
        
        profile_options = ["TURBO", "FAST", "SAFE", "CAREFUL", "ULTRA"]
        self.profile_dropdown = ctk.CTkComboBox(
            profile_frame,
            values=profile_options,
            variable=self.current_profile,
            command=self._on_profile_change,
            width=120
        )
        self.profile_dropdown.pack(side="left")
        self.profile_dropdown.set("SAFE")

    def _build_recommendations_panel(self, parent):
        """Build recommendations panel"""
        card = SectionCard(parent)
        card.pack(fill="both", expand=True)

        TitleLabel(card.inner_frame, text="Recommendations").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Recommendations list
        self.recommendations_text = ctk.CTkTextbox(
            card.inner_frame,
            height=200,
            font=(FONT_FAMILY, 12)
        )
        self.recommendations_text.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
        self.recommendations_text.configure(state="disabled")

        # Action Buttons
        button_frame = ctk.CTkFrame(card.inner_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        ctk.CTkButton(
            button_frame,
            text="Refresh Analysis",
            command=self._refresh_analysis,
            fg_color=COLORS["brand"],
            text_color=COLORS["text_inverse"],
            width=120
        ).pack(side="left", padx=(0, SPACING["xs"]))
        
        ctk.CTkButton(
            button_frame,
            text="Reset Stats",
            command=self._reset_stats,
            fg_color=COLORS["surface_2"],
            text_color=COLORS["text_primary"],
            width=100
        ).pack(side="left")

    def _create_stat_card(self, parent, row, col, title, value, color):
        """Create a stat card"""
        card = StatCard(parent, label=title, value=value, tone=color)
        card.grid(row=row, column=col, padx=SPACING["xs"], pady=SPACING["xs"], sticky="ew")
        return card.value

    def _update_loop(self):
        """Background update loop"""
        time.sleep(2)
        while not self.stop_event.is_set():
            try:
                ui_dispatch(self, self._refresh_analysis)
            except Exception as e:
                print(f"ML Analytics update error: {e}")
            self.stop_event.wait(5)

    def _refresh_analysis(self):
        """Refresh risk analysis"""
        try:
            # Get engine stats
            engine_stats = self.engine_service.get_engine_stats()
            
            # Get risk brain stats
            risk_stats = self.risk_brain.get_stats()
            
            # Update risk score
            risk_score = self.risk_brain.calculate_risk()
            self.risk_score_card.configure(text=f"{risk_score}/100")
            
            # Update usage
            hourly = risk_stats.get("hourly_used", 0)
            hourly_limit = risk_stats.get("hourly_limit", 50)
            self.hourly_usage_card.configure(text=f"{hourly}/{hourly_limit}")
            
            daily = risk_stats.get("daily_used", 0)
            daily_limit = risk_stats.get("daily_limit", 400)
            self.daily_usage_card.configure(text=f"{daily}/{daily_limit}")
            
            # Update delay
            avg_delay = risk_stats.get("avg_delay", 0)
            self.delay_card.configure(text=f"{avg_delay:.1f}s")
            
            # Update messages
            messages = risk_stats.get("messages_sent_total", 0)
            self.messages_card.configure(text=str(messages))
            
            # Update pauses
            pauses = risk_stats.get("total_pauses", 0)
            self.pauses_card.configure(text=str(pauses))
            
            # Update factors
            factors = risk_stats.get("risk_factors", {})
            factors_text = "Risk Factors:\n"
            for key, value in factors.items():
                factors_text += f"• {key}: {value}\n"
            self._update_textbox(self.factors_text, factors_text)
            
            # Update ML prediction
            ml_pred = risk_stats.get("risk_factors", {}).get("ml_prediction", "N/A")
            self._update_textbox(self.ml_prediction_text, f"ML Prediction: {ml_pred}")
            
            ml_conf = risk_stats.get("risk_factors", {}).get("ml_confidence", "N/A")
            self._update_textbox(self.ml_confidence_text, f"Confidence: {ml_conf}")
            
            # Update recommendations
            recommendation = self.risk_brain.get_recommendation()
            rec_text = f"Status: {recommendation.get('status', 'N/A')}\n"
            rec_text += f"Action: {recommendation.get('action', 'N/A')}\n"
            rec_text += f"Score: {recommendation.get('risk_score', 0)}/100\n"
            rec_text += f"Suggested Profile: {recommendation.get('suggested_profile', 'N/A')}\n"
            self._update_textbox(self.recommendations_text, rec_text)
            
        except Exception as e:
            print(f"Error refreshing analysis: {e}")

    def _update_textbox(self, textbox, text):
        """Update textbox content safely"""
        try:
            textbox.configure(state="normal")
            textbox.delete("1.0", "end")
            textbox.insert("1.0", text)
            textbox.configure(state="disabled")
        except Exception:
            pass

    def _on_profile_change(self, value):
        """Handle profile change"""
        try:
            profile_map = {
                "TURBO": RiskMode.TURBO,
                "FAST": RiskMode.FAST,
                "SAFE": RiskMode.SAFE,
                "CAREFUL": RiskMode.CAREFUL,
                "ULTRA": RiskMode.ULTRA
            }
            mode = profile_map.get(value, RiskMode.SAFE)
            self.risk_brain.set_mode(mode)
            self._refresh_analysis()
        except Exception as e:
            print(f"Error changing profile: {e}")

    def _reset_stats(self):
        """Reset risk statistics"""
        try:
            self.risk_brain.reset()
            self._refresh_analysis()
        except Exception as e:
            print(f"Error resetting stats: {e}")

    def destroy(self):
        """Cleanup when tab is destroyed"""
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
        super().destroy()
