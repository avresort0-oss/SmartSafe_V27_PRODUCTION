#!/bin/bash
# One-click VPS Deploy for SmartSafe V27

set -e

echo "🚀 SmartSafe V27 - One-Click Deploy"
echo "====================================="

# Config
REPO_DIR="/opt/smartsafe"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
BRANCH="main"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Docker & Compose
if ! command -v docker &> /dev/null; then
    error "Docker not installed"
    exit 1
fi
if ! docker compose version &> /dev/null; then
    warn "Docker Compose v2 recommended: https://docs.docker.com/compose/install/"
fi

log "Updating repository..."
cd "$REPO_DIR" || { error "Directory $REPO_DIR not found"; exit 1; }
git checkout "$BRANCH"
git pull origin "$BRANCH"

log "Building & starting services..."
docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" up -d --build

log "Waiting for services to be healthy..."
sleep 10

# Health checks
if curl -f http://localhost:4000/health &>/dev/null; then
    log "✅ WhatsApp Server: OK (port 4000)"
else
    warn "❌ WhatsApp Server health check failed"
fi

if curl -f http://localhost:8000/health &>/dev/null; then
    log "✅ Python GUI/Webhook: OK (port 8000)"
else
    warn "❌ Python GUI health check failed"
fi

log "🚀 SmartSafe V27 deployed!"
log "📱 WhatsApp API: http://localhost:4000"
log "🌐 Webhook API: http://localhost:8000"
log "📁 Sessions: $REPO_DIR/whatsapp-server/sessions/"
log ""
log "Stop: docker compose -f $COMPOSE_FILE down"
log "Logs: docker compose -f $COMPOSE_FILE logs -f"

