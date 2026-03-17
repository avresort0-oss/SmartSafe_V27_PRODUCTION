# Feature Addition Guide - SmartSafe V27

## 🎯 Adding New Features - Step by Step

This guide provides detailed instructions for adding new features to SmartSafe V27.

## 📋 Feature Planning Checklist

Before coding:
- [ ] Define feature requirements
- [ ] Identify affected components
- [ ] Plan UI changes (if any)
- [ ] Consider data storage needs
- [ ] Plan testing approach

## 🔧 Feature Types & Implementation

### 1. Message Processing Features

#### Example: Adding a Spam Detection Engine

**Step 1: Create the Engine**
```python
# core/engine/spam_detection_engine.py
from .engine_service import BaseEngine
import re
import logging

logger = logging.getLogger(__name__)

class SpamDetectionEngine(BaseEngine):
    def __init__(self):
        super().__init__()
        self.name = "spam_detection"
        self.spam_patterns = [
            r'buy now',
            r'click here',
            r'free money',
            r'urgent'
        ]
    
    def process_message(self, message):
        """Process message for spam detection"""
        content = message.get('content', '').lower()
        spam_score = 0
        
        for pattern in self.spam_patterns:
            if re.search(pattern, content):
                spam_score += 1
        
        is_spam = spam_score >= 2
        
        return {
            'engine': self.name,
            'is_spam': is_spam,
            'spam_score': spam_score,
            'confidence': min(spam_score / len(self.spam_patterns), 1.0),
            'action': 'block' if is_spam else 'proceed'
        }
    
    def get_default_config(self):
        return {
            'enabled': True,
            'priority': 2,
            'spam_threshold': 2,
            'custom_patterns': []
        }
```

**Step 2: Register the Engine**
```python
# core/engine/multi_engine.py
from .spam_detection_engine import SpamDetectionEngine

class MultiEngine:
    def __init__(self):
        self.engines = {
            'spam_detection': SpamDetectionEngine(),
            # ... other engines
        }
```

**Step 3: Update Engine Service**
```python
# core/engine/engine_service.py
def process_with_spam_detection(self, message):
    """Process message with spam detection"""
    if 'spam_detection' in self.engines:
        result = self.engines['spam_detection'].process_message(message)
        if result['action'] == 'block':
            return {'blocked': True, 'reason': 'spam_detected'}
    return {'blocked': False}
```

### 2. UI Features

#### Example: Adding a Spam Dashboard Tab

**Step 1: Create the Tab**
```python
# ui/tabs/spam_dashboard_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
from core.tracking.message_tracking_service import MessageTracking
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class SpamDashboardTab:
    def __init__(self, parent):
        self.parent = parent
        self.tracking = MessageTracking()
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        # Main frame
        self.frame = ttk.Frame(self.parent)
        
        # Title
        title_label = ttk.Label(self.frame, text="Spam Detection Dashboard", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=10)
        
        # Stats frame
        stats_frame = ttk.LabelFrame(self.frame, text="Statistics")
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.total_messages_label = ttk.Label(stats_frame, text="Total Messages: 0")
        self.total_messages_label.pack(anchor='w', padx=5, pady=2)
        
        self.spam_count_label = ttk.Label(stats_frame, text="Spam Messages: 0")
        self.spam_count_label.pack(anchor='w', padx=5, pady=2)
        
        self.spam_rate_label = ttk.Label(stats_frame, text="Spam Rate: 0%")
        self.spam_rate_label.pack(anchor='w', padx=5, pady=2)
        
        # Chart frame
        chart_frame = ttk.LabelFrame(self.frame, text="Spam Trends")
        chart_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.setup_chart(chart_frame)
        
        # Controls
        control_frame = ttk.Frame(self.frame)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(control_frame, text="Refresh", 
                  command=self.load_data).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Export Data", 
                  command=self.export_data).pack(side='left', padx=5)
    
    def setup_chart(self, parent):
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, parent)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
    
    def load_data(self):
        """Load spam statistics"""
        # Get data from tracking service
        stats = self.tracking.get_spam_statistics()
        
        # Update labels
        self.total_messages_label.config(text=f"Total Messages: {stats.get('total', 0)}")
        self.spam_count_label.config(text=f"Spam Messages: {stats.get('spam', 0)}")
        
        spam_rate = (stats.get('spam', 0) / max(stats.get('total', 1), 1)) * 100
        self.spam_rate_label.config(text=f"Spam Rate: {spam_rate:.1f}%")
        
        # Update chart
        self.update_chart(stats.get('daily_data', {}))
    
    def update_chart(self, daily_data):
        """Update spam trends chart"""
        self.ax.clear()
        
        dates = list(daily_data.keys())
        spam_counts = [daily_data[date].get('spam', 0) for date in dates]
        total_counts = [daily_data[date].get('total', 0) for date in dates]
        
        self.ax.plot(dates, spam_counts, label='Spam', color='red')
        self.ax.plot(dates, total_counts, label='Total', color='blue')
        self.ax.set_xlabel('Date')
        self.ax.set_ylabel('Count')
        self.ax.set_title('Spam Detection Trends')
        self.ax.legend()
        self.ax.tick_params(axis='x', rotation=45)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def export_data(self):
        """Export spam data to CSV"""
        try:
            data = self.tracking.export_spam_data()
            # Save to file logic here
            messagebox.showinfo("Success", "Data exported successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export data: {str(e)}")
```

**Step 2: Register Tab in Main Application**
```python
# main.py
from ui.tabs.spam_dashboard_tab import SpamDashboardTab

# In create_tabs() method
def create_tabs(self):
    # ... existing tabs ...
    
    # Add spam dashboard tab
    spam_tab = SpamDashboardTab(self.notebook)
    self.notebook.add(spam_tab.frame, text="Spam Dashboard")
```

### 3. Analytics Features

#### Example: Adding Spam Analytics

**Step 1: Extend Tracking Service**
```python
# core/tracking/message_tracking_service.py
class MessageTracking:
    def log_spam_detection(self, message_id, spam_score, is_spam):
        """Log spam detection results"""
        query = """
        INSERT INTO spam_analytics 
        (message_id, spam_score, is_spam, timestamp)
        VALUES (?, ?, ?, ?)
        """
        self.execute_query(query, (message_id, spam_score, is_spam, datetime.now()))
    
    def get_spam_statistics(self):
        """Get spam statistics"""
        query = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_spam = 1 THEN 1 ELSE 0 END) as spam,
            DATE(timestamp) as date
        FROM spam_analytics 
        WHERE timestamp >= date('now', '-30 days')
        GROUP BY DATE(timestamp)
        """
        return self.fetch_all(query)
    
    def export_spam_data(self):
        """Export spam data for analysis"""
        query = """
        SELECT message_id, spam_score, is_spam, timestamp
        FROM spam_analytics
        ORDER BY timestamp DESC
        """
        return self.fetch_all(query)
```

### 4. Configuration Features

#### Example: Adding Spam Settings

**Step 1: Update Configuration**
```python
# core/config.py
def get_spam_config(self):
    """Get spam detection configuration"""
    return {
        'spam_detection': {
            'enabled': self.get('spam_detection.enabled', True),
            'threshold': self.get('spam_detection.threshold', 2),
            'patterns': self.get('spam_detection.patterns', []),
            'auto_block': self.get('spam_detection.auto_block', False)
        }
    }
```

**Step 2: Create Settings UI**
```python
# ui/tabs/spam_settings_tab.py
class SpamSettingsTab:
    def __init__(self, parent):
        self.parent = parent
        self.config = load_config()
        self.setup_ui()
    
    def setup_ui(self):
        self.frame = ttk.Frame(self.parent)
        
        # Enable spam detection
        self.enabled_var = tk.BooleanVar(value=self.config.get('spam_detection.enabled', True))
        ttk.Checkbutton(self.frame, text="Enable Spam Detection", 
                       variable=self.enabled_var).pack(anchor='w', pady=5)
        
        # Threshold
        ttk.Label(self.frame, text="Spam Threshold:").pack(anchor='w')
        self.threshold_var = tk.IntVar(value=self.config.get('spam_detection.threshold', 2))
        ttk.Scale(self.frame, from_=1, to=10, variable=self.threshold_var, 
                 orient='horizontal').pack(fill='x', pady=5)
        
        # Auto block
        self.auto_block_var = tk.BooleanVar(value=self.config.get('spam_detection.auto_block', False))
        ttk.Checkbutton(self.frame, text="Auto-block Spam", 
                       variable=self.auto_block_var).pack(anchor='w', pady=5)
        
        # Save button
        ttk.Button(self.frame, text="Save Settings", 
                  command=self.save_settings).pack(pady=10)
    
    def save_settings(self):
        """Save spam settings"""
        self.config.update({
            'spam_detection.enabled': self.enabled_var.get(),
            'spam_detection.threshold': self.threshold_var.get(),
            'spam_detection.auto_block': self.auto_block_var.get()
        })
        self.config.save()
        messagebox.showinfo("Success", "Settings saved successfully!")
```

## 🔄 Integration Patterns

### Message Flow Integration
```python
# In engine_service.py
def process_message(self, message):
    results = {}
    
    # Process with all enabled engines
    for engine_name, engine in self.engines.items():
        if engine.is_enabled():
            result = engine.process_message(message)
            results[engine_name] = result
            
            # Handle spam detection
            if engine_name == 'spam_detection' and result.get('action') == 'block':
                return {'blocked': True, 'reason': 'spam', 'details': result}
    
    return {'blocked': False, 'results': results}
```

### UI Data Integration
```python
# In UI tab, update data periodically
def refresh_data(self):
    """Refresh dashboard data"""
    self.load_data()
    # Schedule next refresh
    self.parent.after(30000, self.refresh_data)  # Refresh every 30 seconds
```

## 🧪 Testing New Features

### Unit Tests
```python
# tests/test_spam_detection.py
import pytest
from core.engine.spam_detection_engine import SpamDetectionEngine

class TestSpamDetection:
    def setup_method(self):
        self.engine = SpamDetectionEngine()
    
    def test_spam_detection(self):
        message = {'content': 'Buy now! Free money! Click here!'}
        result = self.engine.process_message(message)
        
        assert result['is_spam'] == True
        assert result['spam_score'] >= 2
        assert result['action'] == 'block'
    
    def test_non_spam_message(self):
        message = {'content': 'Hello, how are you?'}
        result = self.engine.process_message(message)
        
        assert result['is_spam'] == False
        assert result['action'] == 'proceed'
```

### Integration Tests
```python
# tests/test_feature_integration.py
def test_spam_integration():
    """Test spam detection integration with main flow"""
    engine_service = EngineService()
    
    spam_message = {'content': 'Buy now! Free money!'}
    result = engine_service.process_message(spam_message)
    
    assert result['blocked'] == True
    assert result['reason'] == 'spam'
```

## 📝 Documentation Updates

After adding features:
1. Update `DEVELOPER_GUIDE.md`
2. Update `AI_QUICK_START.md`
3. Add feature-specific documentation
4. Update API contracts if needed

## 🚀 Deployment Checklist

Before deploying new features:
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Configuration validated
- [ ] Performance tested
- [ ] Security reviewed
- [ ] Backup created

---

**Ready to add amazing features! 🎉**
