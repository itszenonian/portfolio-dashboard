#!/bin/bash
# Step 1 of 2 — Install Nginx + self-signed HTTPS (works right now, no domain needed)
# After this runs, your dashboard is at https://<your-vm-ip>
# Browser will show a warning — click "Advanced → Proceed" — data is still encrypted.
#
# When you're ready for a real cert (no warning), run upgrade_to_letsencrypt.sh
set -e

CERT_DIR="/etc/ssl/portfolio"
NGINX_CONF="/etc/nginx/sites-available/portfolio"

echo "=== Portfolio Dashboard — HTTPS Setup (self-signed) ==="

# 1. Install Nginx
echo "[1/4] Installing Nginx..."
sudo apt-get update -q
sudo apt-get install -y nginx

# 2. Generate self-signed certificate (valid 1 year)
echo "[2/4] Generating self-signed certificate..."
sudo mkdir -p "$CERT_DIR"
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out    "$CERT_DIR/cert.pem" \
    -subj   "/CN=portfolio-dashboard" \
    2>/dev/null
sudo chmod 600 "$CERT_DIR/key.pem"

# 3. Write Nginx config
echo "[3/4] Configuring Nginx..."
sudo tee "$NGINX_CONF" > /dev/null <<'EOF'
# Redirect all HTTP to HTTPS
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS — reverse proxy to portfolio server on localhost:8765
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/ssl/portfolio/cert.pem;
    ssl_certificate_key /etc/ssl/portfolio/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;

    # Increase timeout for /refresh (generate_dashboard.py can take ~60s)
    proxy_read_timeout 200s;
    proxy_connect_timeout 10s;

    location / {
        proxy_pass         http://127.0.0.1:8765;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
    }
}
EOF

# Enable the site
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/portfolio
sudo rm -f /etc/nginx/sites-enabled/default   # remove nginx default page

# Test config
sudo nginx -t

# 4. Start / reload Nginx
echo "[4/4] Starting Nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

# Get the VM's external IP
VM_IP=$(curl -sf --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo " HTTPS is live!"
echo " URL: https://$VM_IP"
echo ""
echo " NOTE: Your browser will show a security warning"
echo " because this is a self-signed certificate."
echo " Click: Advanced → Proceed to $VM_IP"
echo ""
echo " To remove the warning permanently, run:"
echo "   bash upgrade_to_letsencrypt.sh yourdomain.duckdns.org"
echo "=============================================="
echo ""
echo "IMPORTANT — GCE firewall: make sure ports 80 and 443 are open."
echo "In GCE console: VPC Network → Firewall → Add rule:"
echo "  Name: allow-https  |  Ports: tcp:80,443  |  Targets: All instances"
