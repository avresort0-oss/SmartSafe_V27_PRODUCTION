# SmartSafe V27 - Developer Guide

## 🚀 Quick Overview

SmartSafe V27 is a WhatsApp automation platform with AI-powered message processing, multi-engine support, and advanced analytics. Built with Python (backend) and Node.js (WhatsApp server).

## 📁 Project Structure

```
SmartSafe_V27/
├── main.py                 # Main application entry point
├── core/                   # Core business logic
│   ├── api/               # API services (WhatsApp, Node)
│   ├── engine/            # Message processing engines
│   ├── tracking/          # Message tracking & analytics
│   └── utils/             # Utility functions
├── ui/                    # User interface
│   ├── tabs/              # UI tabs for different features
│   ├── theme/             # UI theming system
│   └── utils/             # UI utilities
├── whatsapp-server/       # Node.js WhatsApp server
├── tests/                 # Test files
└── logs/                  # Application logs
```

## 🏗️ Architecture

### Core Components

1. **Main Application (`main.py`)**
   - Entry point and UI initialization
   - Tab management and navigation
   - Global configuration loading

2. **API Layer (`core/api/`)**
   - `node_service.py` - Node.js communication
   - `whatsapp_baileys.py` - WhatsApp Baileys integration
   - `NODE_CONTRACTS.md` - API contracts documentation

3. **Engine Layer (`core/engine/`)**
   - `engine_service.py` - Main engine coordinator
   - `multi_engine.py` - Multi-engine management
   - `ml_risk_engine.py` - ML-based risk assessment
   - `hybrid_ai.py` - AI message processing
   - `content_policy.py` - Content filtering
   - `compliance.py` - Compliance checking

4. **Tracking Layer (`core/tracking/`)**
   - `message_tracking_service.py` - Message tracking
   - `response_analytics.py` - Response analytics
   - `response_monitor.py` - Response monitoring

5. **UI Layer (`ui/`)**
   - `tabs/` - Individual UI components
   - `theme/` - Design system and theming
   - `utils/` - UI helper functions

## 🔧 Adding New Features

### Step 1: Choose Component Type

**For new message processing logic:**
- Add to `core/engine/`
- Extend `engine_service.py`
- Update `multi_engine.py` if needed

**For new API integrations:**
- Add to `core/api/`
- Follow existing service patterns
- Update `NODE_CONTRACTS.md`

**For new UI features:**
- Add tab to `ui/tabs/`
- Update `main.py` tab registration
- Follow existing UI patterns

**For new analytics:**
- Add to `core/tracking/`
- Integrate with existing tracking services

### Step 2: Implementation Template

#### New Engine Example
```python
# core/engine/my_new_engine.py
from .engine_service import BaseEngine

class MyNewEngine(BaseEngine):
    def __init__(self):
        super().__init__()
        self.name = "MyNewEngine"
    
    def process_message(self, message):
        # Your processing logic here
        return processed_result
    
    def get_config(self):
        # Return engine configuration
        return config
```

#### New UI Tab Example
```python
# ui/tabs/my_new_tab.py
import tkinter as tk
from tkinter import ttk

class MyNewTab:
    def __init__(self, parent):
        self.parent = parent
        self.setup_ui()
    
    def setup_ui(self):
        # Your UI setup here
        frame = ttk.Frame(self.parent)
        frame.pack(fill='both', expand=True)
```

### Step 3: Registration

**Register Engine:**
```python
# In core/engine/multi_engine.py
from .my_new_engine import MyNewEngine

# Add to engines list
self.engines['my_new'] = MyNewEngine()
```

**Register UI Tab:**
```python
# In main.py
from ui.tabs.my_new_tab import MyNewTab

# Add to tab creation
my_new_tab = MyNewTab(notebook)
notebook.add(my_new_tab.frame, text="My New Feature")
```

## 🔌 Key APIs

### WhatsApp API
```python
from core.api.whatsapp_baileys import WhatsAppService

wa_service = WhatsAppService()
wa_service.send_message(number, message)
wa_service.get_contacts()
```

### Engine Service
```python
from core.engine.engine_service import EngineService

engine = EngineService()
result = engine.process_with_engines(message, engines=['ai', 'ml'])
```

### Tracking Service
```python
from core.tracking.message_tracking_service import MessageTracking

tracker = MessageTracking()
tracker.log_message(message_id, content, timestamp)
```

## 🎨 UI Development

### Design System
- Located in `ui/theme/`
- Uses `design_tokens.py` for consistent styling
- Font management via `font_manager.py`

### UI Patterns
- All tabs inherit from base patterns
- Use `ttk` widgets for consistency
- Follow existing naming conventions

## 📊 Configuration

### Main Config
- `settings.json` - Global settings
- `accounts_config.json` - Account configurations
- `.env.example` - Environment variables template

### Engine Config
Each engine can have its own configuration:
```python
# In engine class
def get_default_config(self):
    return {
        'enabled': True,
        'priority': 1,
        'settings': {}
    }
```

## 🧪 Testing

### Running Tests
```bash
python -m pytest tests/
```

### Test Structure
- `tests/` directory contains all test files
- Follow naming pattern: `test_*.py`
- Use pytest framework

## 📝 Logging

### Log Files
- Located in `logs/` directory
- Main log: `logs/smartsafe_YYYYMMDD.log`
- Use Python logging module

### Adding Logs
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Feature activated")
logger.error("Error occurred", exc_info=True)
```

## 🚀 Deployment

### Environment Setup
1. Install Python dependencies: `pip install -r requirements.txt`
2. Setup Node.js server in `whatsapp-server/`
3. Configure environment variables
4. Run `python main.py`

### Production Considerations
- Use `verify_system.py` for system checks
- Monitor logs in `logs/` directory
- Regular database backups from `logs/` folder

## 🔍 Debugging

### Common Issues
1. **WhatsApp Connection**: Check Node.js server status
2. **Engine Failures**: Verify engine configurations
3. **UI Issues**: Check theme and font loading

### Debug Tools
- `verify_system.py` - System verification
- `check_connection.py` - Connection testing
- Log files in `logs/` directory

## 📚 Important Files

| File | Purpose |
|------|---------|
| `main.py` | Application entry point |
| `core/config.py` | Global configuration |
| `core/api/NODE_CONTRACTS.md` | API documentation |
| `ui/theme/design_tokens.py` | UI design system |
| `requirements.txt` | Python dependencies |
| `settings.json` | Application settings |

## 🎯 Best Practices

1. **Code Style**: Follow PEP 8 for Python code
2. **Error Handling**: Use proper exception handling
3. **Logging**: Add appropriate logging for debugging
4. **Testing**: Write tests for new features
5. **Documentation**: Update this guide for new features

## 🆘 Getting Help

1. Check existing code patterns in similar components
2. Review `NODE_CONTRACTS.md` for API specifications
3. Use `verify_system.py` for system diagnostics
4. Check log files for error details

---

**Happy Coding! 🎉**
