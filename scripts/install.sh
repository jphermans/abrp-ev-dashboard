#!/bin/bash
# ═════════════════════════════════════════════════════════════════
# ABRP EV Dashboard — Installer for Raspberry Pi 4/5
# ═════════════════════════════════════════════════════════════════
set -e

INSTALL_DIR="${1:-$HOME/abrp-dashboard}"
SERVICE_NAME="abrp-dashboard"
PORT="${ABRP_PORT:-8000}"

echo "╔════════════════════════════════════════════════════╗"
echo "║   🚗 ABRP EV Dashboard — Pi Installer              ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Detect Pi model
if [ -f /proc/device-tree/model ]; then
  PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
  echo "📋 Detected: $PI_MODEL"
else
  PI_MODEL="Unknown"
  echo "📋 Not a Raspberry Pi (but will install anyway)"
fi

echo "📁 Install dir: $INSTALL_DIR"
echo "🌐 Port: $PORT"
echo ""

# ─── Step 1: Copy files ───────────────────────────────────────────
echo "▶ Step 1/5: Copying files..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/server.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/data"
echo "   ✅ Files copied to $INSTALL_DIR"

# ─── Step 2: Python venv + deps ──────────────────────────────────
echo "▶ Step 2/5: Setting up Python environment..."
if command -v python3 &>/dev/null; then
  echo "   Python3: $(python3 --version)"
else
  echo "   ❌ Python3 not found. Install with: sudo apt install python3 python3-venv"
  exit 1
fi

if [ ! -d "$INSTALL_DIR/venv" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
  echo "   ✅ Virtual environment created"
else
  echo "   ♻️  Using existing venv"
fi

echo "   Installing dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --quiet flask openpyxl weconnect 2>&1 | tail -2
echo "   ✅ Dependencies installed"

# ─── Step 3: Create data directory + copy Excel files ────────────
echo "▶ Step 3/5: Setting up data directory..."
mkdir -p "$INSTALL_DIR/data"

# Copy any Excel files from script dir
shopt -s nullglob
EXCEL_FILES=("$SCRIPT_DIR"/*.xlsx)
if [ ${#EXCEL_FILES[@]} -gt 0 ]; then
  for f in "${EXCEL_FILES[@]}"; do
    cp "$f" "$INSTALL_DIR/data/"
    echo "   📂 Copied: $(basename "$f")"
  done
fi
shopt -u nullglob

echo "   ✅ Data directory ready"

# ─── Step 4: Create systemd service ──────────────────────────────
echo "▶ Step 4/5: Creating autostart service..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > /tmp/abrp-dashboard.service << EOF
[Unit]
Description=ABRP EV Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
Environment=PORT=$PORT
Environment=HOST=0.0.0.0
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if sudo cp /tmp/abrp-dashboard.service "$SERVICE_FILE" 2>/dev/null; then
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  echo "   ✅ Autostart service created and enabled"
  echo "   📌 Service: sudo systemctl {start|stop|status} $SERVICE_NAME"
else
  echo "   ⚠️  Could not create systemd service (not root). Manual start:"
  echo "      cd $INSTALL_DIR && PORT=$PORT ./venv/bin/python server.py"
fi
rm -f /tmp/abrp-dashboard.service

# ─── Step 5: Start and verify ────────────────────────────────────
echo "▶ Step 5/5: Starting service..."

if [ -f "$SERVICE_FILE" ]; then
  sudo systemctl restart "$SERVICE_NAME"
  sleep 2
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "   ✅ Service running!"
  else
    echo "   ⚠️  Service failed to start. Check: sudo journalctl -u $SERVICE_NAME -f"
  fi
else
  # Start in background (no systemd)
  cd "$INSTALL_DIR"
  PORT=$PORT nohup ./venv/bin/python server.py > "$INSTALL_DIR/server.log" 2>&1 &
  echo $! > "$INSTALL_DIR/server.pid"
  sleep 2
  echo "   ✅ Server started (PID: $(cat "$INSTALL_DIR/server.pid"))"
fi

# Get IP
IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║   ✅ Installation Complete!                        ║"
echo "╠════════════════════════════════════════════════════╣"
echo "║                                                    ║"
echo "║   🌐 Open in browser:                              ║"
echo "║      http://$IP:$PORT"
echo "║      http://localhost:$PORT"
echo "║                                                    ║"
echo "║   📂 Files:      $INSTALL_DIR"
echo "║   📊 Data:       $INSTALL_DIR/data/"
echo "║   📋 Upload:     Put .xlsx files in data/ folder   ║"
echo "║                  or use the Upload button          ║"
echo "║                                                    ║"
echo "║   🔧 Commands:                                     ║"
echo "║      sudo systemctl status $SERVICE_NAME"
echo "║      sudo systemctl restart $SERVICE_NAME"
echo "║      sudo journalctl -u $SERVICE_NAME -f           ║"
echo "║                                                    ║"
echo "╚════════════════════════════════════════════════════╝"
