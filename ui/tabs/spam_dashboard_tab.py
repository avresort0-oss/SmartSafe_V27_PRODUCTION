import customtkinter as ctk
from tkinter import messagebox
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from core.tracking.message_tracking_service import MessageTracking

class SpamDashboardTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        # self.tracking = MessageTracking()
        self.setup_ui()
        # self.load_data()

    def setup_ui(self):
        # Title
        title_label = ctk.CTkLabel(self, text="Spam Detection Dashboard", font=('Arial', 16, 'bold'))
        title_label.pack(pady=10)

        # Stats frame
        stats_frame = ctk.CTkFrame(self)
        stats_frame.pack(fill='x', padx=10, pady=5)

        self.total_messages_label = ctk.CTkLabel(stats_frame, text="Total Messages: 0")
        self.total_messages_label.pack(anchor='w', padx=5, pady=2)

        self.spam_count_label = ctk.CTkLabel(stats_frame, text="Spam Messages: 0")
        self.spam_count_label.pack(anchor='w', padx=5, pady=2)

        self.spam_rate_label = ctk.CTkLabel(stats_frame, text="Spam Rate: 0%")
        self.spam_rate_label.pack(anchor='w', padx=5, pady=2)

        # Chart frame
        chart_frame = ctk.CTkFrame(self)
        chart_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # self.setup_chart(chart_frame)

        # Controls
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill='x', padx=10, pady=5)

        # refresh_button = ctk.CTkButton(control_frame, text="Refresh", command=self.load_data)
        # refresh_button.pack(side='left', padx=5)

        # export_button = ctk.CTkButton(control_frame, text="Export Data", command=self.export_data)
        # export_button.pack(side='left', padx=5)

    # def setup_chart(self, parent):
    #     self.fig, self.ax = plt.subplots(figsize=(8, 4))
    #     self.canvas = FigureCanvasTkAgg(self.fig, parent)
    #     self.canvas.get_tk_widget().pack(fill='both', expand=True)

    # def load_data(self):
    #     """Load spam statistics"""
    #     stats = self.tracking.get_spam_statistics()
    #     self.total_messages_label.configure(text=f"Total Messages: {stats.get('total', 0)}")
    #     self.spam_count_label.configure(text=f"Spam Messages: {stats.get('spam', 0)}")
    #     spam_rate = (stats.get('spam', 0) / max(stats.get('total', 1), 1)) * 100
    #     self.spam_rate_label.configure(text=f"Spam Rate: {spam_rate:.1f}%")
    #     self.update_chart(stats.get('daily_data', {}))

    # def update_chart(self, daily_data):
    #     """Update spam trends chart"""
    #     self.ax.clear()
    #     dates = list(daily_data.keys())
    #     spam_counts = [daily_data[date].get('spam', 0) for date in dates]
    #     total_counts = [daily_data[date].get('total', 0) for date in dates]
    #     self.ax.plot(dates, spam_counts, label='Spam', color='red')
    #     self.ax.plot(dates, total_counts, label='Total', color='blue')
    #     self.ax.set_xlabel('Date')
    #     self.ax.set_ylabel('Count')
    #     self.ax.set_title('Spam Detection Trends')
    #     self.ax.legend()
    #     self.ax.tick_params(axis='x', rotation=45)
    #     self.fig.tight_layout()
    #     self.canvas.draw()

    # def export_data(self):
    #     """Export spam data to CSV"""
    #     try:
    #         data = self.tracking.export_spam_data()
    #         # Save to file logic here
    #         messagebox.showinfo("Success", "Data exported successfully!")
    #     except Exception as e:
    #         messagebox.showerror("Error", f"Failed to export data: {str(e)}")
