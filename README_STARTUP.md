# SmartSafe V27 - One-Click Startup Guide

## 🚀 Quick Start

### Option 1: One-Click Start (Recommended)
1. Double-click `install_dependencies.bat` (first time only)
2. Double-click `start_smartsafe.bat`
3. Wait for all services to start (takes ~30-60 seconds)
4. SmartSafe GUI will open automatically

### Option 2: Manual Start
```bash
# Install dependencies (choose one method)
pip install -r requirements_no_compile.txt  # No compilation needed
# OR
.\install_dependencies.bat  # Automated installer

# Install Node.js dependencies
cd whatsapp-server && npm install && cd ..

# Start services
start_smartsafe.bat
```

### Option 3: If Compilation Errors Occur
If you get Microsoft Visual C++ errors:
1. Install Visual C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Or use the no-compile requirements: `pip install -r requirements_no_compile.txt`
3. Run `install_dependencies.bat` for automated handling

## 🛑 Stopping Services
Double-click `stop_services.bat` to cleanly shut down all services.

## 📊 Service URLs
- **WhatsApp Server**: http://localhost:4000
- **Health Check**: http://localhost:4000/health
- **Metrics**: http://localhost:8001/metrics
- **Main GUI**: Starts automatically

## 🔧 Configuration
Edit `.env` file for:
- API keys (Google Cloud, Twilio, etc.)
- Redis settings
- Server ports

## 📋 Prerequisites
- Python 3.8+
- Node.js 16+
- Redis (optional, auto-fallback)
- Google Cloud credentials (for AI features)

## ✨ Features Included
- ✅ Async processing for high performance
- ✅ Redis caching for analytics
- ✅ Circuit breaker for API resilience
- ✅ Prometheus metrics & Jaeger tracing
- ✅ Voice bot (Twilio + Google Speech)
- ✅ Image recognition (Google Vision)
- ✅ Multi-language support (Google Translate)
- ✅ Connection pooling

## 🐛 Troubleshooting

### GUI Closes Immediately
If the GUI opens and then closes immediately:

1. **Run the GUI test first:**
   ```cmd
   python test_gui.py
   ```
   If this shows errors, there are import/initialization issues.

2. **Try alternative GUI startup:**
   ```cmd
   start_gui_separate.bat
   ```
   This starts GUI in a completely separate window.

3. **Check Windows-specific issues:**
   - Make sure you're not running as administrator (can cause issues)
   - Try running `python main.py` directly from command prompt
   - Check if antivirus is blocking the application

4. **Debug mode:**
   ```cmd
   debug_gui.bat
   ```
   This shows detailed error output.

### Other Issues
- If GUI doesn't start, check Python dependencies
- If server fails, check Node.js installation
- View logs in terminal windows
- Use `stop_services.bat` to clean restart
- If compilation errors persist, use `install_dependencies.bat`