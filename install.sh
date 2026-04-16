#!/bin/bash
# ============================================================
#  FRIDAY — One-line Mac Installer
#  Usage: bash install.sh
#  Installs all dependencies, sets up pm2 auto-start on boot
# ============================================================

set -e

FRIDAY_DIR="$HOME/Documents/FRIDAY"
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

header() { echo -e "\n${CYAN}${BOLD}▸ $1${RESET}"; }
ok()     { echo -e "  ${GREEN}✓ $1${RESET}"; }
warn()   { echo -e "  ${YELLOW}⚠ $1${RESET}"; }
fail()   { echo -e "  ${RED}✗ $1${RESET}"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║          FRIDAY — AI Assistant               ║${RESET}"
echo -e "${BOLD}║          FileFlow Inc. Installer             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Check Python ──────────────────────────────────────────
header "Checking Python"
if ! command -v python3 &>/dev/null; then
    fail "Python 3 not found. Install from https://python.org"
fi
PYVER=$(python3 --version 2>&1)
ok "Found $PYVER"

# ── 2. Install Python deps ───────────────────────────────────
header "Installing Python packages"
pip3 install --break-system-packages --quiet \
    python-telegram-bot \
    openai \
    anthropic \
    fastapi \
    "uvicorn[standard]" \
    websockets \
    python-dotenv \
    httpx \
    requests \
    sib-api-v3-sdk 2>&1 | tail -3
ok "Python packages ready"

# ── 3. Check Node + npm (for pm2) ───────────────────────────
header "Checking Node.js"
if ! command -v node &>/dev/null; then
    warn "Node.js not found — installing via Homebrew..."
    if ! command -v brew &>/dev/null; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install node
fi
ok "Node $(node --version) found"

# ── 4. Install pm2 ──────────────────────────────────────────
header "Setting up pm2 (process manager)"
if ! command -v pm2 &>/dev/null; then
    npm install -g pm2 --quiet
    ok "pm2 installed"
else
    ok "pm2 already installed ($(pm2 --version))"
fi

# ── 5. Check .env ────────────────────────────────────────────
header "Checking configuration"
ENV_FILE="$FRIDAY_DIR/config/.env"
if [ ! -f "$ENV_FILE" ]; then
    mkdir -p "$FRIDAY_DIR/config"
    cat > "$ENV_FILE" << 'ENVEOF'
TELEGRAM_BOT_TOKEN=your_token_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
BREVO_API_KEY=your_key_here
GOOGLE_PLACES_API_KEY=your_key_here
COMPANY_EMAIL=support@yourcompany.com
ENVEOF
    warn ".env file created at $ENV_FILE"
    warn "⚠  Add your API keys before starting FRIDAY!"
else
    ok ".env found"
    # Validate required keys are not placeholders
    if grep -q "your_token_here" "$ENV_FILE" || grep -q "your_key_here" "$ENV_FILE"; then
        warn "Some API keys still have placeholder values — update $ENV_FILE"
    fi
fi

# ── 6. Create required directories ───────────────────────────
header "Creating directories"
mkdir -p "$FRIDAY_DIR/logs" "$FRIDAY_DIR/leads" "$FRIDAY_DIR/output"
ok "Directories ready"

# ── 7. Write pm2 ecosystem file ──────────────────────────────
header "Writing pm2 config"
cat > "$FRIDAY_DIR/ecosystem.config.js" << PMEOF
module.exports = {
  apps: [{
    name: 'FRIDAY',
    script: 'main.py',
    interpreter: 'python3',
    cwd: '$FRIDAY_DIR',
    watch: false,
    autorestart: true,
    restart_delay: 3000,
    max_restarts: 10,
    env: {
      PYTHONUNBUFFERED: '1',
    },
    log_file: '$FRIDAY_DIR/logs/pm2.log',
    error_file: '$FRIDAY_DIR/logs/pm2-error.log',
    out_file: '$FRIDAY_DIR/logs/pm2-out.log',
  }]
}
PMEOF
ok "pm2 config written"

# ── 8. Stop any existing FRIDAY process ──────────────────────
header "Preparing to launch"
pm2 stop FRIDAY 2>/dev/null || true
pm2 delete FRIDAY 2>/dev/null || true

# ── 9. Start FRIDAY ──────────────────────────────────────────
header "Starting FRIDAY"
cd "$FRIDAY_DIR"
pm2 start ecosystem.config.js
ok "FRIDAY started"

# ── 10. Auto-start on Mac login ──────────────────────────────
header "Setting up auto-start on login"
pm2 save
# Generate launchctl startup script
STARTUP=$(pm2 startup launchd -u "$USER" --hp "$HOME" 2>&1 | grep "sudo" | tail -1)
if [ -n "$STARTUP" ]; then
    echo -e "\n  ${YELLOW}Run this command to enable auto-start on login:${RESET}"
    echo -e "  ${BOLD}$STARTUP${RESET}\n"
else
    ok "Auto-start configured"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║  ✅  FRIDAY is online!                       ║${RESET}"
echo -e "${BOLD}║                                              ║${RESET}"
echo -e "${BOLD}║  Dashboard  →  http://localhost:7771         ║${RESET}"
echo -e "${BOLD}║  Telegram   →  active (check bot)            ║${RESET}"
echo -e "${BOLD}║                                              ║${RESET}"
echo -e "${BOLD}║  Useful commands:                            ║${RESET}"
echo -e "${BOLD}║    pm2 status         → check FRIDAY         ║${RESET}"
echo -e "${BOLD}║    pm2 logs FRIDAY    → view live logs       ║${RESET}"
echo -e "${BOLD}║    pm2 restart FRIDAY → restart              ║${RESET}"
echo -e "${BOLD}║    pm2 stop FRIDAY    → stop                 ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# Open dashboard in browser
sleep 2
open "http://localhost:7771" 2>/dev/null || true
