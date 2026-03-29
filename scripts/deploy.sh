#!/usr/bin/env bash
# Keleur deployment script — run on the Oracle Cloud VM
set -euo pipefail

echo "=== Keleur deployment ==="

# System packages
echo ">>> Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv git

# Clone or update repo
if [ -d /opt/keleur/.git ]; then
    echo ">>> Updating existing repo..."
    cd /opt/keleur
    sudo -u keleur git pull --ff-only || true
else
    echo ">>> Cloning repo..."
    sudo rm -rf /opt/keleur
    sudo git clone https://github.com/Hug0oO/keleur.git /opt/keleur
fi

# Create keleur user if not exists
if ! id -u keleur &>/dev/null; then
    echo ">>> Creating keleur user..."
    sudo useradd -r -s /bin/false -d /opt/keleur keleur
fi

sudo chown -R keleur:keleur /opt/keleur

# Python venv
echo ">>> Setting up Python venv..."
sudo -u keleur python3 -m venv /opt/keleur/.venv
sudo -u keleur /opt/keleur/.venv/bin/pip install --quiet -r /opt/keleur/requirements.txt

# Data directory
sudo -u keleur mkdir -p /opt/keleur/data

# Systemd service — single process: API + collector in one
echo ">>> Installing systemd service..."

sudo tee /etc/systemd/system/keleur.service > /dev/null << 'UNIT'
[Unit]
Description=Keleur — transport reliability tracker (API + collector)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=keleur
WorkingDirectory=/opt/keleur
ExecStart=/opt/keleur/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/keleur/data

[Install]
WantedBy=multi-user.target
UNIT

# Remove old separate services if they exist
sudo systemctl stop keleur-collector 2>/dev/null || true
sudo systemctl stop keleur-api 2>/dev/null || true
sudo systemctl disable keleur-collector 2>/dev/null || true
sudo systemctl disable keleur-api 2>/dev/null || true
sudo rm -f /etc/systemd/system/keleur-collector.service
sudo rm -f /etc/systemd/system/keleur-api.service

sudo systemctl daemon-reload
sudo systemctl enable keleur
sudo systemctl restart keleur

echo ">>> Waiting 8s for service to start..."
sleep 8

echo ""
echo "=== Service status ==="
sudo systemctl status keleur --no-pager -l | head -20

echo ""
echo "=== Quick API test ==="
curl -s http://localhost:8000/api/overview || echo "API not ready yet (may need more time for initial GTFS import)"

echo ""
echo "=== Deployment complete ==="
