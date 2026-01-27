#!/bin/bash
# =============================================================================
# Production Deployment Script for Wikipedia Search Agent
# =============================================================================

set -e

APP_NAME="wikipedia-agent"
# Detect the directory where the script is running
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_DIR="$SCRIPT_DIR"
VENV_DIR="$APP_DIR/venv"
DOMAIN="${1:-your-domain.com}" 

echo "🚀 Starting production deployment for $APP_NAME..."
echo "📂 App Directory: $APP_DIR"

# =============================================================================
# 0. Check for .env file
# =============================================================================
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  .env file not found!"
    if [ -f "$APP_DIR/.env.example" ]; then
        echo "creation .env from .env.example..."
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo "IMPORTANT: Please edit .env with your real API keys before continuing."
        read -p "Press Enter to continue after editing, or Ctrl+C to stop..."
    else
        echo "❌ No .env or .env.example found. Please create a .env file."
        exit 1
    fi
fi

# Load env vars for systemd (optional, but good to verify)
source "$APP_DIR/.env"

# =============================================================================
# 1. System Dependencies (Auto-detecting Package Manager)
# =============================================================================
echo "📦 Installing system dependencies..."

if command -v dnf &> /dev/null; then
    PKG_MGR="dnf"
    echo "Detected dnf (RHEL/CentOS/Oracle/Fedora)"
    sudo dnf install -y nginx certbot python3-certbot-nginx
elif command -v apt-get &> /dev/null; then
    PKG_MGR="apt-get"
    echo "Detected apt-get (Debian/Ubuntu/Linode default)"
    sudo apt-get update
    sudo apt-get install -y nginx certbot python3-certbot-nginx python3-venv
else
    echo "❌ Unsupported package manager. Please install nginx and certbot manually."
    exit 1
fi

# =============================================================================
# 2. Setup Python Environment
# =============================================================================
echo "🐍 Setting up Python environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Upgrade pip and install requirements
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
# Ensure gunicorn is installed
"$VENV_DIR/bin/pip" install gunicorn

# =============================================================================
# 3. Create systemd service (Using Gunicorn)
# =============================================================================
echo "⚙️ Creating systemd service..."

USER_NAME=$(whoami)
GROUP_NAME=$(id -gn)

sudo tee /etc/systemd/system/${APP_NAME}.service > /dev/null <<EOF
[Unit]
Description=Wikipedia Search Agent (MCP + LangGraph)
After=network.target

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment="PATH=${VENV_DIR}/bin:/usr/bin"
# Run Gunicorn with Uvicorn workers
# 4 workers is a good start for a small VM, or 2*CPU + 1
ExecStart=${VENV_DIR}/bin/gunicorn mcp_client:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# =============================================================================
# 4. Create nginx configuration
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

        # Security Headers
        add_header X-Frame-Options "SAMEORIGIN";
        add_header X-XSS-Protection "1; mode=block";
        add_header X-Content-Type-Options "nosniff";

        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

# Remove default nginx config if it exists (avoids conflicts)
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default || true
fi

# =============================================================================
# 5. Enable and start services
# =============================================================================
echo "🔄 Starting services..."

sudo systemctl daemon-reload
sudo systemctl enable ${APP_NAME}
sudo systemctl restart ${APP_NAME}
sudo systemctl enable nginx
sudo systemctl restart nginx

# =============================================================================
# 6. Configure firewall (UFW for Ubuntu, FirewallD for RHEL)
# =============================================================================
echo "🔥 Configuring firewall..."

if command -v ufw &> /dev/null; then
    sudo ufw allow 'Nginx Full'
    sudo ufw allow ssh
    # sudo ufw enable  # Uncomment if UFW is not enabled, careful not to lock yourself out
elif command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
fi

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
