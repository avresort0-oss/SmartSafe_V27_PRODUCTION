"""
SmartSafe V27 - Message Tracking Tab
Real-time message status, response monitoring, and analytics dashboard
with AI-powered insights
"""

import threading
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import customtkinter as ctk

from core.api.whatsapp_baileys import BaileysAPI
from core.tracking.message_tracking_service import get_tracking_service
from core.tracking.response_monitor import get_response_monitor
from core.tracking.response_analytics import get_response_analytics
from core.engine.engine_service import get_engine_service
from core.ai.ai_service import get_ai_service
from core.ai.response_analyzer import get_response_analyzer
from core.ai.predictive_analytics import get_predictive_analytics
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme import (
    COLORS,
    SPACING,
    TYPOGRAPHY,
    heading,
    body,
    SectionCard,
    StatCard,
    TabHeader,
    PrimaryButton,
    SecondaryButton,
    StyledTextbox,
    StyledInput,
)
from ui.theme.leadwave_components import TitleLabel, CaptionLabel

logger = logging.getLogger(__name__)


class MessageTrackingTab(ctk.CTkFrame):
    """Real-time message tracking and response analytics dashboard"""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        # Services
        self.api = BaileysAPI()
        self.tracking_service = get_tracking_service()
        self.response_monitor = get_response_monitor()
        self.response_analytics = get_response_analytics()
        self.engine_service = get_engine_service()
        
        # AI Services
        self.ai_service = get_ai_service()
        self.response_analyzer = get_response_analyzer()
        self.predictive_analytics = get_predictive_analytics()

        # UI State
        self.stop_event = threading.Event()
        # Slightly slower refresh to reduce load and keep UI smooth.
        self.refresh_interval = 6  # seconds
        self.current_campaign = ""
        self.selected_time_range = ctk.StringVar(value="24h")
        self.auto_refresh = ctk.BooleanVar(value=True)

        # Data cache
        self._last_update = None
        self._campaign_list = []
        self._current_data = {}

        self._build_ui()
        self._start_background_tasks()
        # Defer the initial heavy refresh so the tab can render first.
        self.after(400, lambda: ui_dispatch(self, self._refresh_data))

    def _build_ui(self):
        # Header
        header = TabHeader(
            self,
            title="Message Tracking",
            subtitle="Real-time message status and response analytics",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Toolbar
        self._build_toolbar(header)

        # Main content area
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        # Left panel - Stats and status
        left_panel = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, SPACING["xs"]))

        # Right panel - Details and analytics
        right_panel = ctk.CTkFrame(content_frame, fg_color="transparent")
        right_panel.pack(side="right", fill="both", expand=True, padx=(SPACING["xs"], 0))

        # Build panels
        self._build_status_panel(left_panel)
        self._build_analytics_panel(right_panel)
        self._build_ai_insights_panel(right_panel)
        self._build_prediction_panel(right_panel)
        self._build_details_panel(right_panel)

    def _build_toolbar(self, parent):
        """Build toolbar with controls"""
        toolbar = ctk.CTkFrame(parent.actions, fg_color="transparent")
        toolbar.pack(side="right")

        # Auto-refresh toggle
        refresh_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        refresh_frame.pack(side="right", padx=(SPACING["xs"], 0))
        
        ctk.CTkCheckBox(
            refresh_frame,
            text="Auto Refresh",
            variable=self.auto_refresh,
            command=self._toggle_auto_refresh
        ).pack(side="right")

        # Time range selector
        range_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        range_frame.pack(side="right", padx=(SPACING["sm"], SPACING["xs"]))
        
        CaptionLabel(range_frame, text="Time Range").pack(side="left", padx=(0, SPACING["xs"]))
        self.range_selector = ctk.CTkSegmentedButton(
            range_frame,
            values=["1h", "6h", "24h", "7d"],
            variable=self.selected_time_range,
            command=self._on_time_range_change
        )
        self.range_selector.pack(side="left")

        # Campaign selector
        campaign_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        campaign_frame.pack(side="right", padx=(SPACING["sm"], SPACING["xs"]))
        
        CaptionLabel(campaign_frame, text="Campaign").pack(side="left", padx=(0, SPACING["xs"]))
        self.campaign_selector = ctk.CTkComboBox(
            campaign_frame,
            values=["All Campaigns", "Live Node Data"],
            command=self._on_campaign_change,
            width=150
        )
        self.campaign_selector.pack(side="left")
        self.campaign_selector.set("All Campaigns")

        # Action buttons
        button_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        button_frame.pack(side="right", padx=(SPACING["sm"], SPACING["xs"]))
        
        SecondaryButton(
            button_frame,
            text="Export",
            command=self._export_data,
            width=80
        ).pack(side="left", padx=(0, SPACING["xs"]))
        
        PrimaryButton(
            button_frame,
            text="Refresh",
            command=self._refresh_data,
            width=80
        ).pack(side="left")

    def _build_status_panel(self, parent):
        """Build status overview panel"""
        # Status Cards
        status_card = SectionCard(parent)
        status_card.pack(fill="x", pady=(0, SPACING["md"]))

        TitleLabel(status_card.inner_frame, text="Campaign Status").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Stats grid
        stats_grid = ctk.CTkFrame(status_card.inner_frame, fg_color="transparent")
        stats_grid.pack(fill="x", pady=(0, SPACING["sm"]))
        
        # Configure grid
        for i in range(3):
            stats_grid.grid_columnconfigure(i, weight=1)

        # Create stat cards
        self.total_sent_label = self._create_stat_card(stats_grid, 0, 0, "Total Sent", "0", COLORS["brand"])
        self.delivered_label = self._create_stat_card(stats_grid, 1, 0, "Delivered", "0", COLORS["success"])
        self.responses_label = self._create_stat_card(stats_grid, 2, 0, "Responses", "0", COLORS["warning"])
        
        self.response_rate_label = self._create_stat_card(stats_grid, 0, 1, "Response Rate", "0%", COLORS["text_primary"])
        self.avg_response_time_label = self._create_stat_card(stats_grid, 1, 1, "Avg Response", "0m", COLORS["text_secondary"])
        self.failed_label = self._create_stat_card(stats_grid, 2, 1, "Failed", "0", COLORS["danger"])

        # Real-time status
        realtime_card = SectionCard(parent)
        realtime_card.pack(fill="x", pady=(0, SPACING["md"]))

        rt_header = ctk.CTkFrame(realtime_card.inner_frame, fg_color="transparent")
        rt_header.pack(fill="x", pady=(0, SPACING["sm"]))
        TitleLabel(rt_header, text="Real-time Activity").pack(side="left")
        SecondaryButton(
            rt_header,
            text="Clear All",
            command=self._clear_activity_log,
            width=80,
            height=24
        ).pack(side="right")

        # Activity log
        self.activity_log = StyledTextbox(
            realtime_card.inner_frame,
            height=150,
            font=body(TYPOGRAPHY["mono"])
        )
        self.activity_log.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))
        self.activity_log.configure(state="disabled")

    def _build_analytics_panel(self, parent):
        """Build analytics panel"""
        analytics_card = SectionCard(parent)
        analytics_card.pack(fill="x", pady=(0, SPACING["md"]))

        TitleLabel(analytics_card.inner_frame, text="Response Analytics").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Response distribution
        response_frame = ctk.CTkFrame(analytics_card.inner_frame, fg_color="transparent")
        response_frame.pack(fill="x", pady=(0, SPACING["sm"]))
        
        CaptionLabel(response_frame, text="Response Types").pack(anchor="w")
        self.response_types_text = ctk.CTkTextbox(
            response_frame,
            height=80,
            font=body(TYPOGRAPHY["body"])
        )
        self.response_types_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.response_types_text.configure(state="disabled")

        # Sentiment analysis
        sentiment_frame = ctk.CTkFrame(analytics_card.inner_frame, fg_color="transparent")
        sentiment_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(sentiment_frame, text="Sentiment Analysis").pack(anchor="w")
        self.sentiment_text = ctk.CTkTextbox(
            sentiment_frame,
            height=80,
            font=body(TYPOGRAPHY["body"])
        )
        self.sentiment_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.sentiment_text.configure(state="disabled")

        # Peak hours
        hours_frame = ctk.CTkFrame(analytics_card.inner_frame, fg_color="transparent")
        hours_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(hours_frame, text="Peak Response Hours").pack(anchor="w")
        self.peak_hours_text = ctk.CTkTextbox(
            hours_frame,
            height=60,
            font=body(TYPOGRAPHY["body"])
        )
        self.peak_hours_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.peak_hours_text.configure(state="disabled")

    def _build_ai_insights_panel(self, parent):
        """Build AI-powered insights panel"""
        ai_card = SectionCard(parent)
        ai_card.pack(fill="x", pady=(0, SPACING["md"]))

        # Header with AI indicator
        ai_header = ctk.CTkFrame(ai_card.inner_frame, fg_color="transparent")
        ai_header.pack(fill="x", pady=(0, SPACING["sm"]))
        
        TitleLabel(ai_header, text="AI Insights").pack(side="left")
        
        # AI status indicator
        if self.ai_service.enabled:
            ai_status = ctk.CTkLabel(
                ai_header,
                text="● Active",
                text_color=COLORS["success"],
                font=body(TYPOGRAPHY["caption"])
            )
        else:
            ai_status = ctk.CTkLabel(
                ai_header,
                text="○ Setup Required",
                text_color=COLORS["text_muted"],
                font=body(TYPOGRAPHY["caption"])
            )
        ai_status.pack(side="right")

        # Key themes
        themes_frame = ctk.CTkFrame(ai_card.inner_frame, fg_color="transparent")
        themes_frame.pack(fill="x", pady=(0, SPACING["sm"]))
        
        CaptionLabel(themes_frame, text="Key Themes").pack(anchor="w")
        self.ai_themes_text = ctk.CTkTextbox(
            themes_frame,
            height=60,
            font=body(TYPOGRAPHY["body"])
        )
        self.ai_themes_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.ai_themes_text.configure(state="disabled")

        # AI Summary
        summary_frame = ctk.CTkFrame(ai_card.inner_frame, fg_color="transparent")
        summary_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(summary_frame, text="AI Summary").pack(anchor="w")
        self.ai_summary_text = ctk.CTkTextbox(
            summary_frame,
            height=80,
            font=body(TYPOGRAPHY["body"])
        )
        self.ai_summary_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.ai_summary_text.configure(state="disabled")

        # Recommendations
        rec_frame = ctk.CTkFrame(ai_card.inner_frame, fg_color="transparent")
        rec_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(rec_frame, text="Recommendations").pack(anchor="w")
        self.ai_recommendations_text = ctk.CTkTextbox(
            rec_frame,
            height=60,
            font=body(TYPOGRAPHY["body"])
        )
        self.ai_recommendations_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.ai_recommendations_text.configure(state="disabled")

    def _build_prediction_panel(self, parent):
        """Build prediction panel"""
        pred_card = SectionCard(parent)
        pred_card.pack(fill="x", pady=(0, SPACING["md"]))

        TitleLabel(pred_card.inner_frame, text="Predictions").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Predicted response rate
        pred_stats_grid = ctk.CTkFrame(pred_card.inner_frame, fg_color="transparent")
        pred_stats_grid.pack(fill="x", pady=(0, SPACING["sm"]))
        
        for i in range(2):
            pred_stats_grid.grid_columnconfigure(i, weight=1)

        self.pred_response_rate = self._create_stat_card(pred_stats_grid, 0, 0, "Predicted Rate", "0%", COLORS["brand"])
        self.pred_confidence = self._create_stat_card(pred_stats_grid, 0, 1, "Confidence", "0%", COLORS["text_secondary"])

        # Best time
        best_time_frame = ctk.CTkFrame(pred_card.inner_frame, fg_color="transparent")
        best_time_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(best_time_frame, text="Best Send Time").pack(anchor="w")
        self.best_time_text = ctk.CTkTextbox(
            best_time_frame,
            height=40,
            font=body(TYPOGRAPHY["body"])
        )
        self.best_time_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.best_time_text.configure(state="disabled")

        # Risk assessment
        risk_frame = ctk.CTkFrame(pred_card.inner_frame, fg_color="transparent")
        risk_frame.pack(fill="x", pady=(SPACING["sm"], 0))
        
        CaptionLabel(risk_frame, text="Risk Level").pack(anchor="w")
        self.risk_text = ctk.CTkTextbox(
            risk_frame,
            height=40,
            font=body(TYPOGRAPHY["body"])
        )
        self.risk_text.pack(fill="x", pady=(SPACING["xs"], 0))
        self.risk_text.configure(state="disabled")

    def _build_details_panel(self, parent):
        """Build detailed message list panel"""
        details_card = SectionCard(parent)
        details_card.pack(fill="both", expand=True)

        TitleLabel(details_card.inner_frame, text="Message Details").pack(anchor="w", pady=(0, SPACING["sm"]))

        # Controls
        controls_frame = ctk.CTkFrame(details_card.inner_frame, fg_color="transparent")
        controls_frame.pack(fill="x", pady=(0, SPACING["sm"]))

        # Search
        search_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        search_frame.pack(side="left", fill="x", expand=True)
        
        CaptionLabel(search_frame, text="Search:").pack(side="left", padx=(0, SPACING["xs"]))
        self.search_entry = StyledInput(
            search_frame,
            placeholder_text="Search by phone or content..."
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search)

        # Filter
        filter_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        filter_frame.pack(side="right", padx=(SPACING["sm"], 0))
        
        self.status_filter = ctk.CTkComboBox(
            filter_frame,
            values=["All", "Sent", "Delivered", "Read", "Failed", "Responded"],
            command=self._on_status_filter,
            width=120
        )
        self.status_filter.pack(side="left")
        self.status_filter.set("All")

        # Message list
        self.message_list_frame = ctk.CTkScrollableFrame(
            details_card.inner_frame,
            fg_color="transparent",
            height=300
        )
        self.message_list_frame.pack(fill="both", expand=True)

        # Loading indicator
        self.loading_label = ctk.CTkLabel(
            self.message_list_frame,
            text="Loading messages...",
            text_color=COLORS["text_muted"]
        )
        self.loading_label.pack(pady=SPACING["lg"])

    def _create_stat_card(self, parent, row, col, title, value, color):
        """Create a stat card"""
        card = StatCard(parent, label=title, value=value, tone=color)
        card.grid(row=row, column=col, padx=SPACING["xs"], pady=SPACING["xs"], sticky="ew")
        return card.value

    def _start_background_tasks(self):
        """Start background monitoring and refresh tasks"""
        # Start response monitoring
        try:
            self.response_monitor.start_monitoring()
        except Exception as e:
            self._log_activity(f"Failed to start response monitoring: {e}")

        # Start auto-refresh loop
        if self.auto_refresh.get():
            start_daemon(self._auto_refresh_loop)

        # Register for tracking events
        self.tracking_service.add_event_callback(self._on_tracking_event)

    def _auto_refresh_loop(self):
        """Background auto-refresh loop"""
        while not self.stop_event.is_set():
            try:
                if self.auto_refresh.get():
                    ui_dispatch(self, self._refresh_data)
                time.sleep(self.refresh_interval)
            except Exception as e:
                logger.error(f"Error in auto-refresh loop: {e}")
                time.sleep(10)

    def _refresh_data(self):
        """Refresh all data"""
        try:
            # Get time range in hours
            time_range_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
            hours = time_range_map.get(self.selected_time_range.get(), 24)

            # Get analytics data
            analytics_campaign_id = None if self.current_campaign in ["All Campaigns", "Live Node Data"] else self.current_campaign
            metrics = self.response_analytics.get_response_metrics(analytics_campaign_id, hours)

            # Update UI
            self._update_stats(metrics)
            self._update_analytics(metrics)
            
            list_campaign_id = self.current_campaign if self.current_campaign != "All Campaigns" else None
            self._update_message_list(list_campaign_id, hours)
            
            # Update AI insights (in background to not block UI)
            self._update_ai_insights(analytics_campaign_id, hours)
            
            # Update predictions
            self._update_predictions(analytics_campaign_id)

            # Update last update time
            self._last_update = datetime.now(timezone.utc)

        except Exception as e:
            self._log_activity(f"Error refreshing data: {e}")

    def _update_stats(self, metrics):
        """Update statistics display"""
        self.total_sent_label.configure(text=str(metrics.total_responses))
        self.delivered_label.configure(text=str(int(metrics.response_rate * metrics.total_responses / 100)) if metrics.total_responses > 0 else "0")
        self.responses_label.configure(text=str(metrics.total_responses))
        self.response_rate_label.configure(text=f"{metrics.response_rate:.1f}%")
        self.avg_response_time_label.configure(text=f"{metrics.avg_response_time_minutes:.1f}m")
        
        # Calculate failed (this would need to be implemented in tracking service)
        failed_count = max(0, metrics.total_responses - int(metrics.response_rate * metrics.total_responses / 100))
        self.failed_label.configure(text=str(failed_count))

    def _update_analytics(self, metrics):
        """Update analytics display"""
        # Response types
        response_text = "Response Distribution:\n"
        for response_type, count in metrics.response_distribution.items():
            percentage = (count / metrics.total_responses * 100) if metrics.total_responses > 0 else 0
            response_text += f"• {response_type}: {count} ({percentage:.1f}%)\n"
        
        self.response_types_text.configure(state="normal")
        self.response_types_text.delete("1.0", "end")
        self.response_types_text.insert("1.0", response_text)
        self.response_types_text.configure(state="disabled")

        # Sentiment
        sentiment_text = "Sentiment Distribution:\n"
        for sentiment, count in metrics.sentiment_distribution.items():
            percentage = (count / metrics.total_responses * 100) if metrics.total_responses > 0 else 0
            sentiment_text += f"• {sentiment}: {count} ({percentage:.1f}%)\n"
        
        self.sentiment_text.configure(state="normal")
        self.sentiment_text.delete("1.0", "end")
        self.sentiment_text.insert("1.0", sentiment_text)
        self.sentiment_text.configure(state="disabled")

        # Peak hours
        hours_text = "Peak Response Hours:\n"
        for hour in metrics.peak_response_hours:
            hours_text += f"• {hour:02d}:00 - {hour+1:02d}:00\n"
        
        self.peak_hours_text.configure(state="normal")
        self.peak_hours_text.delete("1.0", "end")
        self.peak_hours_text.insert("1.0", hours_text)
        self.peak_hours_text.configure(state="disabled")

    def _update_ai_insights(self, campaign_id: Optional[str], hours: int):
        """Update AI-powered insights"""
        try:
            # Get bulk response analysis
            report = self.response_analyzer.analyze_responses_bulk(campaign_id, hours)
            
            # Update themes
            themes_text = "Key Themes:\n"
            for theme in report.key_themes[:5]:
                themes_text += f"• {theme}\n"
            
            self.ai_themes_text.configure(state="normal")
            self.ai_themes_text.delete("1.0", "end")
            self.ai_themes_text.insert("1.0", themes_text if themes_text != "Key Themes:\n" else "No themes detected yet")
            self.ai_themes_text.configure(state="disabled")
            
            # Update summary
            summary_text = report.overall_summary if report.overall_summary else "Analyzing responses..."
            
            self.ai_summary_text.configure(state="normal")
            self.ai_summary_text.delete("1.0", "end")
            self.ai_summary_text.insert("1.0", summary_text)
            self.ai_summary_text.configure(state="disabled")
            
            # Update recommendations
            rec_text = "Recommendations:\n"
            for rec in report.recommendations[:3]:
                rec_text += f"• {rec}\n"
            
            self.ai_recommendations_text.configure(state="normal")
            self.ai_recommendations_text.delete("1.0", "end")
            self.ai_recommendations_text.insert("1.0", rec_text if rec_text != "Recommendations:\n" else "No recommendations yet")
            self.ai_recommendations_text.configure(state="disabled")
            
        except Exception as e:
            logger.error(f"Error updating AI insights: {e}")

    def _update_predictions(self, campaign_id: Optional[str]):
        """Update prediction data"""
        try:
            # Get performance prediction
            prediction = self.predictive_analytics.predict_performance(campaign_id)
            
            # Update prediction stats
            self.pred_response_rate.configure(text=f"{prediction.predicted_response_rate:.1f}%")
            self.pred_confidence.configure(text=f"{prediction.confidence * 100:.0f}%")
            
            # Update best time
            best_time_text = f"Best: {prediction.best_send_time}\nDay: {prediction.best_send_day}"
            
            self.best_time_text.configure(state="normal")
            self.best_time_text.delete("1.0", "end")
            self.best_time_text.insert("1.0", best_time_text)
            self.best_time_text.configure(state="disabled")
            
            # Update risk assessment
            risk = self.predictive_analytics.get_risk_assessment(campaign_id)
            
            risk_text = f"Level: {risk.get('risk_level', 'Unknown').upper()}\n"
            for factor in risk.get('risk_factors', [])[:2]:
                risk_text += f"• {factor}\n"
            
            self.risk_text.configure(state="normal")
            self.risk_text.delete("1.0", "end")
            self.risk_text.insert("1.0", risk_text)
            self.risk_text.configure(state="disabled")
            
        except Exception as e:
            logger.error(f"Error updating predictions: {e}")

    def _update_message_list(self, campaign_id: Optional[str], hours: int):
        """Update message list display"""
        # Clear existing items
        for widget in self.message_list_frame.winfo_children():
            widget.destroy()

        # Get messages
        try:
            if campaign_id == "Live Node Data":
                resp = self.api.get_all_tracked_messages()
                if resp.get("ok"):
                    raw_messages = resp.get("messages", {})
                    if isinstance(raw_messages, dict):
                        raw_messages = list(raw_messages.values())
                    messages = self._convert_node_messages(raw_messages)
                else:
                    messages = []
            elif campaign_id:
                messages = self.tracking_service.get_messages_by_campaign(campaign_id)
            else:
                # Get recent messages
                messages = self.tracking_service.get_recent_messages(days=max(1, hours // 24))
            
            if not messages:
                no_data_label = ctk.CTkLabel(
                    self.message_list_frame,
                    text="No messages found",
                    text_color=COLORS["text_muted"]
                )
                no_data_label.pack(pady=SPACING["lg"])
                return

            # Display messages
            for message in messages[:50]:  # Limit to 50 for performance
                self._create_message_item(message)

        except Exception as e:
            logger.error(f"Error loading messages: {e}")
            error_label = ctk.CTkLabel(
                self.message_list_frame,
                text=f"Error loading messages: {e}",
                text_color=COLORS["danger"]
            )
            error_label.pack(pady=SPACING["lg"])

    def _convert_node_messages(self, node_messages):
        """Convert raw Node messages to UI-compatible objects"""
        class MessageItem:
            def __init__(self, data):
                self.contact_phone = (
                    data.get("phoneNumber")
                    or data.get("to")
                    or data.get("phone")
                    or ""
                )
                self.delivery_status = data.get("status") or data.get("delivery_status") or "pending"
                self.message_content = data.get("content") or data.get("message") or ""
                self.response_received = False
                self.response_content = ""
        
        return [MessageItem(m) for m in node_messages]

    def _create_message_item(self, message):
        """Create a message item in the list"""
        item_frame = ctk.CTkFrame(
            self.message_list_frame,
            fg_color=COLORS["surface_2"],
            corner_radius=SPACING["xs"]
        )
        item_frame.pack(fill="x", padx=SPACING["xs"], pady=2)

        # Status indicator
        status_colors = {
            "sent": COLORS["brand"],
            "delivered": COLORS["success"],
            "read": COLORS["success"],
            "failed": COLORS["danger"],
            "pending": COLORS["text_muted"]
        }
        
        status_color = status_colors.get(message.delivery_status, COLORS["text_muted"])
        
        # Message info
        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.pack(fill="x", padx=SPACING["sm"], pady=SPACING["xs"])

        # Phone and status
        top_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        top_row.pack(fill="x")
        
        ctk.CTkLabel(
            top_row,
            text=message.contact_phone,
            font=body(TYPOGRAPHY["body"], "bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left")

        status_label = ctk.CTkLabel(
            top_row,
            text=message.delivery_status.upper(),
            font=body(TYPOGRAPHY["caption"]),
            text_color=status_color,
            fg_color=status_color.replace("1", "0.2")  # Lighter background
        )
        status_label.pack(side="right", padx=(SPACING["xs"], 0))

        # Message preview
        preview = message.message_content[:50] + "..." if len(message.message_content) > 50 else message.message_content
        ctk.CTkLabel(
            info_frame,
            text=preview,
            font=body(TYPOGRAPHY["caption"]),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        # Response info
        if message.response_received:
            response_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            response_frame.pack(fill="x", pady=(SPACING["xs"], 0))
            
            response_preview = message.response_content[:30] + "..." if message.response_content and len(message.response_content) > 30 else message.response_content
            ctk.CTkLabel(
                response_frame,
                text=f"↩ {response_preview}",
                font=body(TYPOGRAPHY["caption"], "italic"),
                text_color=COLORS["brand"]
            ).pack(anchor="w")

    def _on_tracking_event(self, event):
        """Handle tracking events"""
        ui_dispatch(self, lambda: self._log_activity(f"{event.event_type}: {event.message_id}"))

    def _clear_activity_log(self):
        """Clear the activity log"""
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.configure(state="disabled")

    def _log_activity(self, message):
        """Log activity to the activity log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.activity_log.configure(state="normal")
        self.activity_log.insert("end", log_entry)
        self.activity_log.see("end")
        
        # Keep log size manageable
        lines = self.activity_log.get("1.0", "end").split('\n')
        if len(lines) > 100:
            self.activity_log.delete("1.0", "2.0")
        
        self.activity_log.configure(state="disabled")

    def _toggle_auto_refresh(self):
        """Toggle auto-refresh"""
        # The background loop is started once in _start_background_tasks;
        # here we only toggle the flag to avoid spawning extra threads.
        if self.auto_refresh.get():
            self._log_activity("Auto-refresh enabled")
        else:
            self._log_activity("Auto-refresh disabled")

    def _on_time_range_change(self, value):
        """Handle time range change"""
        self._refresh_data()

    def _on_campaign_change(self, value):
        """Handle campaign change"""
        self.current_campaign = value
        self._refresh_data()

    def _on_search(self, event):
        """Handle search"""
        # This would filter the message list
        pass

    def _on_status_filter(self, value):
        """Handle status filter"""
        # This would filter the message list by status
        pass

    def _export_data(self):
        """Export tracking data"""
        try:
            campaign_id = None if self.current_campaign == "All Campaigns" else self.current_campaign
            
            if campaign_id:
                # Export campaign data
                csv_data = self.tracking_service.export_campaign_data(campaign_id, "csv")
                
                # Save to file
                from tkinter import filedialog
                filename = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
                )
                
                if filename:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(csv_data)
                    
                    self._log_activity(f"Exported data to {filename}")
            else:
                self._log_activity("Please select a campaign to export")
                
        except Exception as e:
            self._log_activity(f"Export failed: {e}")

    def destroy(self):
        """Clean up resources when the tab is destroyed."""
        if hasattr(self, "stop_event"):
            self.stop_event.set()
        try:
            self.response_monitor.stop_monitoring()
        except Exception:
            pass
        # tracking_service / engine_service are shared singletons; do not hard-stop them here.
        super().destroy()


# Add to main.py tab configuration
# This will be added to the tab list in main.py
