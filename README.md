# SmartSafe V27 - Professional WhatsApp Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)
[![Render](https://img.shields.io/badge/Deploy-Render-orange.svg?logo=render)](https://render.com)
[![Railway](https://img.shields.io/badge/Deploy-Railway-blue.svg?logo=railway)](https://railway.app)

SmartSafe V27 is a **production-ready WhatsApp automation suite** with:

- 🎨 Modern Python desktop GUI (CustomTkinter)
- ⚡ Node.js WhatsApp server (WhiskeySockets/Baileys)
- 🤖 Multi-account, bulk messaging, analytics
- 🛡️ Smart anti-ban, proxy rotation, spam detection

## ✨ One-Click Docker Deploy

```bash
git clone <your-repo>
cd SmartSafe_V27_PRODUCTION
docker compose up -d --build
```

- WhatsApp API: `http://localhost:4000`
- Webhook API: `http://localhost:8000`

## ☁️ Cloud One-Click Deploy

| Platform | Deploy |
|----------|--------|
| [Render](https://render.com/deploy-docker?repo=<your-repo>) | Use `render.yaml` |
| [Railway](https://railway.app/new) | Use `railway.json` |
| VPS | `./deploy.sh` |

## 🚀 Quick Start (Native)

### Windows

1. Double-click `ONE_CLICK_SETUP_AND_RUN.bat`
2. Or: `START_SMARTSAFE_ONE_CLICK.bat`

### Docker (Recommended)

```bash
docker compose up -d
```

### Manual

```bash
# Terminal 1: WhatsApp Server
cd whatsapp-server && npm install && node index.js

# Terminal 2: GUI
pip install -r requirements.txt
python main.py
```

## 📋 Features

- ✅ Multi-Account QR Login
- ✅ Bulk Sender + Templates
- ✅ Profile Checker (Bulk)
- ✅ Smart Balancer & Proxy Rotation
- ✅ ML Analytics & Spam Detection
- ✅ Flow Builder & Auto-Reply
- ✅ Message Tracking Dashboard

## 🛠 Environment Variables

Copy `.env.example` → `.env`:

```
SMARTSAFE_API_KEY=yourkey
SMARTSAFE_NODE_HOST=localhost
SMARTSAFE_WEBHOOK_API_ENABLED=true
```

## 🔧 VPS Deploy

```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

## 📚 Documentation

- [Project Overview](docs/PROJECT_OVERVIEW.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [AI Quick Start](docs/AI_QUICK_START.md)

## 🧪 Health Checks

```bash
curl http://localhost:4000/health  # WhatsApp Server
curl http://localhost:8000/health  # Webhook API
```

## 🔒 License

MIT License - see [LICENSE](LICENSE)

## 🙌 Support

[GitHub Issues](https://github.com/yourusername/SmartSafe_V27_PRODUCTION/issues)

---
⭐ Star on GitHub if useful!
