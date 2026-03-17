import customtkinter as ctk
import threading
import time
import random

from ui.theme.design_tokens import COLORS, TYPOGRAPHY, SPACING
from ui.theme.leadwave_components import (
    SectionCard,
    StatCard,
    TitleLabel,
    CaptionLabel,
    TabHeader,
    StatusBadge,
)
from core.api.whatsapp_baileys import BaileysAPI
from ui.utils.threading_helpers import start_daemon, ui_dispatch

FONT_FAMILY = TYPOGRAPHY.get("font_family", "Inter")


class DashboardTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.api = BaileysAPI()
        self.chart_bars = []
        self.kpi_labels = {}
        self.stop_event = threading.Event()
        self.time_range = ctk.StringVar(value="24h")
        self.start_time = time.time()

        # Derived metrics for richer KPIs
        self._prev_total_sent = 0
        self._prev_total_errors = 0
        self._prev_refresh_ts: float | None = None

        # Header
        header = TabHeader(
            self,
            title="Dashboard",
            subtitle="Real-time metrics and system overview",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Status Badge
        self.status_badge = StatusBadge(header.actions, text="LIVE", tone="success", pulse=True)
        self.status_badge.pack(side="right")

        # KPI Section
        self.kpi_container = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_container.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.kpi_container.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # Primary delivery funnel metrics
        self._create_kpi_card(self.kpi_container, 0, "Total Sent", "0", "---", "info")
        self._create_kpi_card(self.kpi_container, 1, "Success Rate", "---", "---", "success")
        self._create_kpi_card(self.kpi_container, 2, "Active Sessions", "0/0", "---", "warning")
        self._create_kpi_card(self.kpi_container, 3, "Total Errors", "0", "---", "danger")
        self._create_kpi_card(self.kpi_container, 4, "Throughput (msg/min)", "–", "—", "info")

        # Main Content Area
        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.content_area.grid_columnconfigure(0, weight=3)  # Chart
        self.content_area.grid_columnconfigure(1, weight=2)  # Status
        self.content_area.grid_rowconfigure(0, weight=1)

        # Chart Panel
        self._create_chart_panel(self.content_area)

        # Status Panel
        self._create_status_panel(self.content_area)

        # Start background update loop
        start_daemon(self.data_update_loop)

    def _create_kpi_card(self, parent, col, title, value, trend, tone):
        card = StatCard(parent, label=title, value=value, tone=tone)
        card.grid(row=0, column=col, sticky="ew", padx=SPACING["sm"])

        trend_color = {
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "danger": COLORS["danger"],
        }.get(tone, COLORS["info"])

        trend_label = ctk.CTkLabel(
            card.inner_frame,
            text=trend,
            font=(FONT_FAMILY, 13, "bold"),
            text_color=trend_color,
        )
        trend_label.pack(anchor="w", pady=(4, 0))

        self.kpi_labels[title] = {"value": card.value, "trend": trend_label}

    def _create_chart_panel(self, parent):
        panel = SectionCard(parent, fg_color=COLORS["surface_1"], border_width=0)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]), pady=0)

        header = ctk.CTkFrame(panel.inner_frame, fg_color="transparent")
        header.pack(fill="x", pady=(SPACING["xs"], SPACING["sm"]))

        TitleLabel(header, text="Traffic Overview").pack(side="left")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")

        CaptionLabel(right, text="Time range").pack(side="left", padx=(0, SPACING["xs"]))
        self.range_selector = ctk.CTkSegmentedButton(
            right,
            values=["1h", "24h", "7d"],
            variable=self.time_range,
            command=lambda _value: None,  # Visual only for now; API is aggregate.
        )
        self.range_selector.pack(side="left")

        # Chart Container
        chart_frame = ctk.CTkFrame(panel.inner_frame, fg_color="transparent")
        chart_frame.pack(fill="both", expand=True, pady=(SPACING["xs"], 0))

        # Simulated Bar Chart
        initial_data = [random.uniform(0.1, 0.8) for _ in range(12)]
        hours = ["00", "02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22"]

        self.chart_bars.clear()

        for i, val in enumerate(initial_data):
            bar_group = ctk.CTkFrame(chart_frame, fg_color="transparent")
            bar_group.pack(side="left", fill="both", expand=True, padx=4)

            # Bar wrapper for bottom alignment
            wrapper = ctk.CTkFrame(bar_group, fg_color="transparent")
            wrapper.pack(side="top", fill="both", expand=True)

            # The Bar
            bar = ctk.CTkProgressBar(
                wrapper,
                orientation="vertical",
                progress_color=COLORS["brand"],
                fg_color=COLORS["surface_3"],
                corner_radius=4,
                width=8,
            )
            bar.pack(side="bottom", fill="y", expand=True)
            bar.set(val)
            self.chart_bars.append(bar)

            # Label
            ctk.CTkLabel(
                bar_group,
                text=hours[i],
                font=(FONT_FAMILY, 11),
                text_color=COLORS["text_muted"],
            ).pack(side="bottom", pady=(SPACING["xs"], 0))

    def data_update_loop(self):
        """Background thread to fetch and update data."""
        time.sleep(2)  # Initial delay
        while not self.stop_event.is_set():
            try:
                # --- Fetch Real Data ---
                resp = self.api.get_stats()
                stats = resp.get("stats", {}) or {}

                total_sent = 0
                total_errors = 0
                connected_count = 0
                total_accounts = len(stats)

                for acc in stats.values():
                    total_sent += int(acc.get("messages_sent", 0) or 0)
                    total_errors += int(acc.get("errors", 0) or 0)
                    if acc.get("connected"):
                        connected_count += 1

                # Calculate Success Rate
                success_rate = 100.0
                total_ops = total_sent + total_errors
                if total_ops > 0:
                    success_rate = (total_sent / total_ops) * 100

                # Messages / min based on deltas
                now = time.time()
                throughput_display = "–"
                if self._prev_refresh_ts is not None:
                    elapsed = max(0.1, now - self._prev_refresh_ts)
                    delta_sent = max(0, total_sent - self._prev_total_sent)
                    per_min = (delta_sent / elapsed) * 60.0
                    throughput_display = f"{per_min:.1f}"

                self._prev_refresh_ts = now
                self._prev_total_sent = total_sent
                self._prev_total_errors = total_errors

                # Calculate uptime
                elapsed = int(time.time() - self.start_time)
                uptime_str = f"{elapsed // 3600:02}:{(elapsed % 3600) // 60:02}:{elapsed % 60:02}"

                # --- Dispatch UI update ---
                def _update():
                    if not self.winfo_exists():
                        return  # Stop if widget is destroyed

                    # Update chart (Simulate activity visual based on real volume)
                    # We shift bars left and add a new one representing current activity relative to capacity
                    current_bars = [b.get() for b in self.chart_bars]
                    if current_bars:
                        current_bars.pop(0)
                    current_bars.append(
                        random.uniform(0.1, 0.5)
                        if total_sent == 0
                        else random.uniform(0.3, 0.9)
                    )

                    for i, bar in enumerate(self.chart_bars):
                        if i < len(current_bars):
                            bar.set(current_bars[i])

                    # Update KPIs
                    self.kpi_labels["Total Sent"]["value"].configure(text=f"{total_sent:,}")
                    self.kpi_labels["Success Rate"]["value"].configure(text=f"{success_rate:.1f}%")
                    self.kpi_labels["Active Sessions"]["value"].configure(
                        text=f"{connected_count}/{total_accounts}"
                    )
                    self.kpi_labels["Total Errors"]["value"].configure(text=f"{total_errors}")
                    self.kpi_labels["Throughput (msg/min)"]["value"].configure(
                        text=throughput_display
                    )

                    # Update Success trend
                    if success_rate < 90:
                        self.kpi_labels["Success Rate"]["trend"].configure(
                            text="Degraded", text_color=COLORS["warning"]
                        )
                    else:
                        self.kpi_labels["Success Rate"]["trend"].configure(
                            text="Healthy", text_color=COLORS["success"]
                        )

                    # Update Uptime
                    if hasattr(self, 'uptime_pill'):
                        self.uptime_pill.configure(text=f"  {uptime_str}  ")

                if self.winfo_exists():
                    ui_dispatch(self, _update)

            except Exception as e:
                # In a real app, you'd log this
                print(f"Dashboard update error: {e}")

            # Wait for 2 seconds before next update
            self.stop_event.wait(2)

    def _create_status_panel(self, parent):
        panel = SectionCard(parent, fg_color=COLORS["surface_1"])
        panel.grid(row=0, column=1, sticky="nsew")

        TitleLabel(panel.inner_frame, text="System Health").pack(
            anchor="w",
            pady=(0, SPACING["sm"]),
        )

        self._add_health_item(panel.inner_frame, "WhatsApp Server", "Operational", COLORS["success"])
        self._add_health_item(panel.inner_frame, "Message Queue", "Processing", COLORS["brand"])
        self._add_health_item(panel.inner_frame, "Database", "Connected", COLORS["success"])
        self._add_health_item(panel.inner_frame, "Proxy Network", "8 Active", COLORS["warning"])
        self._add_health_item(panel.inner_frame, "Auto-Reply AI", "Standby", COLORS["text_muted"])
        self.uptime_pill = self._add_health_item(panel.inner_frame, "System Uptime", "00:00:00", COLORS["info"])

    def _add_health_item(self, parent, label, status, color):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=SPACING["lg"], pady=SPACING["xs"])

        ctk.CTkLabel(
            row,
            text=label,
            font=(FONT_FAMILY, 14),
            text_color=COLORS["text_secondary"],
        ).pack(side="left")

        # Colored pills use high-contrast inverse text; neutral uses softer surface/background.
        if color == COLORS["text_muted"]:
            pill_fg = COLORS["surface_2"]
            pill_text_color = COLORS["text_secondary"]
        else:
            pill_fg = color
            pill_text_color = COLORS["text_inverse"]

        status_pill = ctk.CTkLabel(
            row,
            text=f"  {status}  ",
            fg_color=pill_fg,
            text_color=pill_text_color,
            font=(FONT_FAMILY, 12, "bold"),
            height=24,
            corner_radius=12,
        )
        status_pill.pack(side="right")
        return status_pill

    def destroy(self):
        """Cleanup when the tab is destroyed."""
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
        try:
            self.api.close()
        except Exception:
            pass
        super().destroy()