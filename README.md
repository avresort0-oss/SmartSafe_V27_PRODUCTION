# SmartSafe V27

SmartSafe V27 is a production-ready WhatsApp automation suite with a Python desktop GUI and a Node.js WhatsApp server (WhiskeySockets/Baileys).

**Prerequisites**
- Python 3.10+
- Node.js 18+

**Quick Start (Windows)**
1. Copy `.env.example` to `.env` and update values as needed. The Node server reads `.env` from the project root or `whatsapp-server/.env`.
2. First-time setup and run: `ONE_CLICK_SETUP_AND_RUN.bat`.
3. Subsequent runs (no installs): `START_SMARTSAFE_ONE_CLICK.bat`.
4. Run components separately if needed: `START_WHATSAPP_SERVER.bat` and `START_SMARTSAFE_GUI.bat`.
5. Stop everything: `STOP_SMARTSAFE.bat`.

**Manual Setup (macOS/Linux)**
1. Install Python deps: `python -m pip install -r requirements.txt`.
2. Install Node deps: `npm install` inside `whatsapp-server`.
3. Start the WhatsApp server: `node whatsapp-server/index.js`.
4. Start the GUI: `python main.py`.

**Docs**
- `docs/PROJECT_OVERVIEW.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/AI_QUICK_START.md`
- `docs/README.md` (WhatsApp server integration details)

**Troubleshooting**
- Verify system dependencies: `verify_system.py`
- Check server connectivity: `check_connection.py`
- Run health checks: `test_health.py`
