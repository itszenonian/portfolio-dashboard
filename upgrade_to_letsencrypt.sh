#!/bin/bash
# Step 2 of 2 — Upgrade to a real Let's Encrypt cert (removes the browser warning)
#
# Before running this, you need a domain pointing to your VM IP.
# Free option: DuckDNS (takes 2 minutes)
#   1. Go to https://www.duckdns.org
#   2. Sign in (Google/GitHub)
#   3. Pick a subdomain, e.g. "zenodash" → zenodash.duckdns.org
#   4. Enter your VM's external IP and click "update ip"
#   5. Wait ~1 minute, then run:
#        bash upgrade_to_letsencrypt.sh zenodash.duckdns.org
#
# Usage: bash upgrade_to_letsencrypt.sh <your-domain>

set -e

DOMAIN="$1"
NGINX_CONF="/etc/nginx/sites-available/portfolio"

if [ -z "$DOMAIN" ]; then
    echo "Usage: bash upgrade_to_letsencrypt.sh <your-domain>"
    echo "Example: bash upgrade_to_letsencrypt.sh zenodash.duckdns.org"
    exit 1
fi

echo "=== Upgrading to Let's Encrypt cert for: $DOMAIN ==="

# 1. Install Certbot
echo "[1/3] Installing Certbot..."
sudo apt-get install -y certbot python3-certbot-nginx

# 2. Update Nginx config with the real domain
echo "[2/3] Updating Nginx server_name to $DOMAIN..."
sudo sed -i "s/server_name _;/server_name $DOMAIN;/g" "$NGINX_CONF"
sudo nginx -t
sudo systemctl reload nginx

# 3. Get the certificate (Certbot handles Nginx config automatically)
echo "[3/3] Requesting certificate from Let's Encrypt..."
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
    --email "mabenotzeno@gmail.com" --redirect

echo ""
echo "=============================================="
echo " Done! Real HTTPS certificate installed."
echo " URL: https://$DOMAIN"
echo ""
echo " Auto-renewal is already configured."
echo " Cert renews automatically every 90 days."
echo "=============================================="
