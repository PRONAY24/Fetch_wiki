#!/bin/bash
# =============================================================================
# Production Deployment Script for Wikipedia Search Agent
# =============================================================================

set -e

APP_NAME="wikipedia-agent"
APP_DIR="/home/opc/Fetch_wiki"
VENV_DIR="$APP_DIR/venv"
DOMAIN="${1:-your-domain.com}"  # Pass domain as argument or edit this

echo "🚀 Starting production deployment..."

# =============================================================================
# 1. System Dependencies
# =============================================================================
echo "📦 Installing system dependencies..."
sudo dnf install -y nginx certbot python3-certbot-nginx --disablerepo=ol9_oci_included || true

# =============================================================================
# 2. Create systemd service for the app
# =============================================================================
echo "⚙️ Creating systemd service..."

sudo tee /etc/systemd/system/${APP_NAME}.service > /dev/null <<EOF
[Unit]
Description=Wikipedia Search Agent (MCP + LangGraph)
After=network.target

[Service]
Type=simple
User=opc
Group=opc
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/bin"
Environment="OPENAI_API_KEY=${OPENAI_API_KEY}"
Environment="OPENAI_MODEL=gpt-4o-mini"
Environment="LOG_LEVEL=INFO"
Environment="HOST=127.0.0.1"
Environment="PORT=8000"
ExecStart=${VENV_DIR}/bin/python mcp_client.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# =============================================================================
# 3. Create nginx configuration
# =============================================================================
echo "🌐 Configuring nginx..."

sudo tee /etc/nginx/conf.d/${APP_NAME}.conf > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

# =============================================================================
# 4. Enable and start services
# =============================================================================
echo "🔄 Starting services..."

sudo systemctl daemon-reload
sudo systemctl enable ${APP_NAME}
sudo systemctl start ${APP_NAME}
sudo systemctl enable nginx
sudo systemctl start nginx

# =============================================================================
# 5. Configure firewall
# =============================================================================
echo "🔥 Configuring firewall..."

sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update your DNS to point ${DOMAIN} to this server's IP"
echo "2. Run: sudo certbot --nginx -d ${DOMAIN}"
echo "3. Check status: sudo systemctl status ${APP_NAME}"
echo "4. View logs: sudo journalctl -u ${APP_NAME} -f"
echo ""
echo "🌐 Your app will be available at: http://${DOMAIN}"
echo "   After SSL setup: https://${DOMAIN}"
