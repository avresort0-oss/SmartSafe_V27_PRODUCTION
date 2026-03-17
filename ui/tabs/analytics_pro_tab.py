import threading
import time

import customtkinter as ctk

from core.api.whatsapp_baileys import BaileysAPI
from core.engine.engine_service import get_engine_service
from ui.utils.threading_helpers import start_daemon, ui_dispatch
from ui.theme import (
    COLORS,
    TYPOGRAPHY,
    SPACING,
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


class AnalyticsProTab(ctk.CTkFrame):
    """Live analytics driven by Node /stats endpoint."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.api = BaileysAPI()
        self.engine_service = get_engine_service()
        self.stop_event = threading.Event()
        self.refresh_interval = 3  # Poll every 3 seconds for real-time updates

        # View-state
        self.time_range = ctk.StringVar(value="24h")
        self.filter_mode = ctk.StringVar(value="all")
        self.search_query = ctk.StringVar(value="")

        # Derived metrics cache so filters/search don't re-hit API.
        self._last_stats: dict | None = None
        self._last_health: dict | None = None
        self._refresh_in_flight = False
        self._prev_total_sent = 0
        self._prev_refresh_ts: float | None = None

        self._build_ui()
        self.refresh()
        start_daemon(self._auto_loop)

    def _build_ui(self):
        # Header
        header = TabHeader(
            self,
            title="Analytics PRO",
            subtitle="Live performance insights for all WhatsApp accounts",
        )
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))

        # Time-range presets (Last 1h / 24h / 7d)
        toolbar = ctk.CTkFrame(header.actions, fg_color="transparent")
        toolbar.pack(side="right")

        buttons_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        buttons_frame.pack(side="right", padx=(SPACING["xs"], 0))
        SecondaryButton(
            buttons_frame,
            text="Reset Data",
            command=self.reset_data,
            width=110,
        ).pack(side="left", padx=(0, SPACING["xs"]))
        PrimaryButton(
            buttons_frame,
            text="Refresh",
            command=self.refresh,
            width=110,
        ).pack(side="left")

        range_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        range_frame.pack(side="right", padx=(0, SPACING["sm"]))
        CaptionLabel(range_frame, text="Time range").pack(side="left", padx=(0, SPACING["xs"]))
        self.range_selector = ctk.CTkSegmentedButton(
            range_frame,
            values=["1h", "24h", "7d"],
            variable=self.time_range,
            command=lambda _value: self._apply_cached_view(),
        )
        self.range_selector.pack(side="left")

        # Stats Cards
        stats_card = SectionCard(self)
        stats_card.pack(
            fill="x",
            padx=SPACING["lg"],
            pady=(0, SPACING["lg"]),
        )
        TitleLabel(
            stats_card.inner_frame,
            text="Overall Performance",
            font=heading(TYPOGRAPHY["h3"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        stats_grid = ctk.CTkFrame(stats_card.inner_frame, fg_color="transparent")
        stats_grid.pack(fill="x")
        stats_grid.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.connected_card = StatCard(stats_grid, "Connected", "0", "success")
        self.messages_card = StatCard(stats_grid, "Messages Sent", "0", "info")
        self.checks_card = StatCard(stats_grid, "Profile Checks", "0", "warning")
        self.errors_card = StatCard(stats_grid, "Errors", "0", "danger")
        self.error_rate_card = StatCard(stats_grid, "Error Rate", "0.0%", "danger")
        self.throughput_card = StatCard(stats_grid, "Messages / min", "–", "info")

        self.connected_card.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xs"]))
        self.messages_card.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])
        self.checks_card.grid(row=0, column=2, sticky="ew", padx=SPACING["xs"])
        self.errors_card.grid(row=0, column=3, sticky="ew", padx=SPACING["xs"])
        self.error_rate_card.grid(row=0, column=4, sticky="ew", padx=SPACING["xs"])
        self.throughput_card.grid(row=0, column=5, sticky="ew", padx=(SPACING["xs"], 0))

        # Risk Card
        risk_card = SectionCard(self)
        risk_card.pack(
            fill="x",
            padx=SPACING["lg"],
            pady=(0, SPACING["lg"]),
        )
        TitleLabel(
            risk_card.inner_frame,
            text="System Risk Level",
            font=heading(TYPOGRAPHY["h3"], "bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, SPACING["sm"]))
        self.risk_label = ctk.CTkLabel(
            risk_card.inner_frame,
            text="LOW",
            font=heading(TYPOGRAPHY["h1"], "bold"),
            text_color=COLORS["success"],
        )
        self.risk_label.pack(pady=(SPACING["xs"], 0))
        CaptionLabel(
            risk_card.inner_frame,
            text="Derived from error rate vs. total traffic and active sessions.",
        ).pack(anchor="w", pady=(SPACING["xs"], 0))
        self.top_risky_caption = CaptionLabel(
            risk_card.inner_frame,
            text="Top risky accounts: –",
        )
        self.top_risky_caption.pack(anchor="w", pady=(SPACING["xxs"], 0))

        # Table Card
        table_card = SectionCard(self)
        table_card.pack(
            fill="both",
            expand=True,
            padx=SPACING["lg"],
            pady=(0, SPACING["lg"]),
        )
        self.table_title_label = TitleLabel(
            table_card.inner_frame,
            text="Per-Account Stats · Last 24h",
            font=heading(TYPOGRAPHY["h3"], "bold"),
            text_color=COLORS["text_secondary"],
        )
        self.table_title_label.pack(anchor="w", pady=(0, SPACING["sm"]))

        # Filters + search row
        controls = ctk.CTkFrame(table_card.inner_frame, fg_color="transparent")
        controls.pack(fill="x", pady=(0, SPACING["sm"]))
        controls.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=0)

        search_entry = StyledInput(
            controls,
            placeholder_text="Search by account ID…",
            textvariable=self.search_query,
        )
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        # Update view as user types without new API call.
        search_entry.bind("<KeyRelease>", lambda _event: self._apply_cached_view())

        filter_frame = ctk.CTkFrame(controls, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="e")
        CaptionLabel(filter_frame, text="Filter").pack(side="left", padx=(0, SPACING["xs"]))
        self.filter_selector = ctk.CTkSegmentedButton(
            filter_frame,
            values=["All", "Connected", "High error"],
            variable=self.filter_mode,
            command=lambda _value: self._apply_cached_view(),
        )
        self.filter_selector.pack(side="left")

        self.table = StyledTextbox(table_card.inner_frame, font=body(TYPOGRAPHY["mono"]))
        self.table.pack(fill="both", expand=True)
        self.table.configure(state="disabled")

    def _auto_loop(self):
        while not self.stop_event.is_set():
            self.refresh(silent=True)
            self.stop_event.wait(self.refresh_interval)

    def _derive_risk(self, connected: int, total_errors: int, total_messages: int) -> tuple[str, str]:
        if total_errors == 0:
            return "LOW", COLORS["success"]

        denominator = max(1, total_messages)
        error_rate = (total_errors / denominator) * 100
        if error_rate < 5 and connected > 0:
            return "MODERATE", COLORS["warning"]
        return "HIGH", COLORS["danger"]

    def _score_account_risk(self, row: dict) -> float:
        """Simple per-account risk score based on errors and connection state."""
        errors = int(row.get("errors", 0) or 0)
        sent = int(row.get("messages_sent", 0) or 0)
        connected = bool(row.get("connected"))
        base = errors * 2
        if not connected:
            base += 5
        if sent > 0:
            base += (errors / max(1, sent)) * 10
        return base

    def refresh(self, silent: bool = False):
        # Debounce to avoid spawning many workers from rapid clicks.
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        start_daemon(self._refresh_worker, silent)

    def _refresh_worker(self, silent: bool = False):
        try:
            resp = self.api.get_stats()
        finally:
            # Ensure flag is cleared even if API raises.
            self._refresh_in_flight = False

        if not resp.get("ok"):
            if not silent:
                ui_dispatch(self, lambda: self._update_table(f"Failed to load stats: {resp.get('error')}"))
            return

        stats = resp.get("stats", {}) or {}
        self._last_stats = stats
        try:
            self._last_health = self.engine_service.get_account_health() or {}
        except Exception:
            self._last_health = {}

        # Aggregate metrics
        connected = 0
        total_sent = 0
        total_checks = 0
        total_errors = 0

        for row in stats.values():
            is_connected = bool(row.get("connected"))
            connected += 1 if is_connected else 0
            total_sent += int(row.get("messages_sent", 0) or 0)
            total_checks += int(row.get("profile_checks", 0) or 0)
            total_errors += int(row.get("errors", 0) or 0)

        # Error rate KPI
        denominator = max(1, total_sent + total_errors)
        error_rate = (total_errors / denominator) * 100

        # Messages / min derived from delta since last refresh
        now = time.time()
        throughput_display = "–"
        if self._prev_refresh_ts is not None:
            elapsed = max(0.1, now - self._prev_refresh_ts)
            delta_sent = max(0, total_sent - self._prev_total_sent)
            per_min = (delta_sent / elapsed) * 60.0
            throughput_display = f"{per_min:.1f}"
        self._prev_refresh_ts = now
        self._prev_total_sent = total_sent

        risk_text, risk_color = self._derive_risk(connected, total_errors, total_sent)

        # Build filtered table view and top risky accounts text.
        lines, top_risky_text = self._build_table_and_risks(stats)

        def _apply():
            # KPIs
            self.connected_card.set_value(str(connected))
            self.messages_card.set_value(str(total_sent))
            self.checks_card.set_value(str(total_checks))
            self.errors_card.set_value(str(total_errors))
            self.error_rate_card.set_value(f"{error_rate:.1f}%")
            self.throughput_card.set_value(throughput_display)

            # Risk summary
            self.risk_label.configure(text=risk_text, text_color=risk_color)
            self.top_risky_caption.configure(text=top_risky_text)

            # Table + title
            range_label = self.time_range.get()
            self.table_title_label.configure(text=f"Per-Account Stats · Last {range_label}")
            self._update_table("\n".join(lines))

        ui_dispatch(self, _apply)

    def _build_table_and_risks(self, stats: dict[str, dict]) -> tuple[list[str], str]:
        """Apply current filters/search to stats and build table + top risky text."""
        health = self._last_health or {}
        lines: list[str] = [
            "account     connected   health  quarantine  status        sent   checks   errors   last_error",
        ]
        lines.append("-" * 104)

        filter_mode = (self.filter_mode.get() or "all").lower()
        query = (self.search_query.get() or "").strip().lower()

        scored_accounts: list[tuple[str, float]] = []

        for account in sorted(stats.keys()):
            if query and query not in account.lower():
                continue

            row = stats.get(account, {})
            is_connected = bool(row.get("connected"))
            errors = int(row.get("errors", 0) or 0)
            sent = int(row.get("messages_sent", 0) or 0)

            # Filter logic
            if filter_mode == "connected" and not is_connected:
                continue
            if filter_mode == "high error":
                # Treat as high-error if error rate >= 5% and at least a few messages.
                denom = max(1, sent)
                if errors < 1 or (errors / denom) * 100 < 5:
                    continue

            last_error = str(row.get("last_error") or "-")
            hrow = health.get(account, {}) if isinstance(health, dict) else {}
            health_score = str(hrow.get("score", "-"))
            q = bool(hrow.get("quarantined", False))
            q_rem = int(hrow.get("quarantine_remaining_s", 0) or 0)
            q_txt = ("YES" if q else "NO") + (f"({q_rem}s)" if q and q_rem > 0 else "")
            lines.append(
                f"{account:<10} {str(is_connected):<10} {health_score:<6} {q_txt:<10} {str(row.get('status', '-')):<12} "
                f"{sent:<6} {int(row.get('profile_checks', 0) or 0):<8} {errors:<7} {last_error[:24]}"
            )

            # Risk scoring for top list (use all accounts, not just filtered ones)
            scored_accounts.append((account, self._score_account_risk(row)))

        # Top 3 risky accounts text
        if scored_accounts:
            scored_accounts.sort(key=lambda item: item[1], reverse=True)
            top = scored_accounts[:3]
            formatted = ", ".join(f"{name} (risk {score:.1f})" for name, score in top if score > 0)
            top_text = f"Top risky accounts: {formatted or '–'}"
        else:
            top_text = "Top risky accounts: –"

        return lines, top_text

    def _apply_cached_view(self):
        """Re-render table and risk summaries from cached stats only."""
        if not self._last_stats:
            return
        lines, top_risky_text = self._build_table_and_risks(self._last_stats)

        def _apply():
            range_label = self.time_range.get()
            self.table_title_label.configure(text=f"Per-Account Stats · Last {range_label}")
            self.top_risky_caption.configure(text=top_risky_text)
            self._update_table("\n".join(lines))

        ui_dispatch(self, _apply)

    def _update_table(self, text: str):
        self.table.configure(state="normal")
        self.table.delete("1.0", "end")
        self.table.insert("1.0", text)
        self.table.configure(state="disabled")

    def reset_data(self):
        # Placeholder for reset logic if API supports it
        self._last_stats = {}
        self._update_table("Data reset (local view cleared). Waiting for new data...")

    def destroy(self):
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
        try:
            self.api.close()
        except Exception:
            pass
        super().destroy()
