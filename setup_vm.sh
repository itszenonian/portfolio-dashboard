#!/bin/bash
# Run this once on your GCE VM to set up the portfolio dashboard.
# Usage: bash setup_vm.sh
set -e

APP_DIR="/opt/portfolio"
SERVICE="portfolio"

echo "=== Portfolio Dashboard — VM Setup ==="

# 1. System deps
echo "[1/5] Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y python3-pip python3-venv

# 2. Copy files
echo "[2/5] Copying app files to $APP_DIR..."
sudo mkdir -p "$APP_DIR"
sudo cp -r ./* "$APP_DIR/"
sudo chown -R "$USER:$USER" "$APP_DIR"

# 3. Python virtual environment
echo "[3/5] Creating Python venv and installing dependencies..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# 4. Systemd service (keeps server.py running 24/7)
echo "[4/5] Installing systemd service..."
sudo tee /etc/systemd/system/$SERVICE.service > /dev/null <<EOF
[Unit]
Description=Portfolio Dashboard Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl start "$SERVICE"

# 5. Cron job — auto-refresh every 30 minutes
echo "[5/5] Setting up cron job (every 30 min)..."
CRON_CMD="*/30 * * * * cd $APP_DIR && $APP_DIR/venv/bin/python generate_dashboard.py >> /var/log/portfolio_refresh.log 2>&1"
( crontab -l 2>/dev/null | grep -v "generate_dashboard"; echo "$CRON_CMD" ) | crontab -

echo ""
echo "======================================"
echo " Done! Dashboard is live."
echo " URL: http://$(curl -s ifconfig.me):8765"
echo " User: admin  (change DASHBOARD_USER in .env)"
echo "======================================"
echo ""
echo "IMPORTANT: Make sure .env has your API keys:"
echo "  BLOCKVISION_API_KEY=..."
echo "  BINANCE_API_KEY=..."
echo "  BINANCE_SECRET_KEY=..."
echo "  DASHBOARD_USER=admin"
echo "  DASHBOARD_PASS=yourpassword"
echo ""
echo "Then run: sudo systemctl restart portfolio"
