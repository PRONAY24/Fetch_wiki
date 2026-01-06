# 🚀 Deployment Guide - Wikipedia Search Agent

This guide explains how to deploy the Wikipedia Search Agent on a Linux server (Ubuntu 22.04/24.04).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Application Deployment](#application-deployment)
4. [Service Configuration](#service-configuration)
5. [Nginx Reverse Proxy](#nginx-reverse-proxy)
6. [SSL/HTTPS Setup](#sslhttps-setup)
7. [Management Commands](#management-commands)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Ubuntu 22.04 or 24.04 LTS server
- SSH access with root privileges
- OpenAI API key
- Domain name (optional, for HTTPS)

### Minimum Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 1 GB | 2 GB |
| CPU | 1 core | 2 cores |
| Storage | 10 GB | 20 GB |

---

## Server Setup

### Step 1: Update System

```bash
apt update && apt upgrade -y
```

**What this does:**
- `apt update` - Downloads the latest package lists from Ubuntu repositories
- `apt upgrade -y` - Installs all available security and software updates
- `-y` flag means "yes to all prompts"

### Step 2: Install Dependencies

```bash
apt install -y python3.12-venv git nginx certbot python3-certbot-nginx
```

**Packages explained:**

| Package | Purpose |
|---------|---------|
| `python3.12-venv` | Create isolated Python environments |
| `git` | Clone repository from GitHub |
| `nginx` | Web server / reverse proxy |
| `certbot` | Obtain free SSL certificates |
| `python3-certbot-nginx` | Auto-configure nginx for HTTPS |

### Step 3: Create Application User

```bash
useradd -m -s /bin/bash appuser
```

**Flags explained:**
- `-m` - Create home directory `/home/appuser`
- `-s /bin/bash` - Set bash as default shell

**Why create a separate user?**
- Security: If the app is compromised, attacker has limited permissions
- Isolation: App can't accidentally modify system files
- Best practice: Never run applications as root

---

## Application Deployment

### Step 4: Clone Repository

```bash
cd /home/appuser
git clone https://github.com/PRONAY24/Fetch_wiki.git
cd Fetch_wiki
```

### Step 5: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**What is a virtual environment?**

A virtual environment is an isolated Python installation. Each project can have its own dependencies without conflicts.

```
/home/appuser/Fetch_wiki/
├── venv/
│   ├── bin/
│   │   ├── python      ← Isolated Python interpreter
│   │   ├── pip         ← Isolated pip
│   │   └── activate    ← Activation script
│   └── lib/
│       └── python3.12/
│           └── site-packages/  ← Project dependencies installed here
├── mcp_client.py
├── mcp_server.py
└── ...
```

### Step 6: Set File Ownership

```bash
chown -R appuser:appuser /home/appuser/Fetch_wiki
```

**Why?** The systemd service runs as `appuser`, so that user must own all project files.

---

## Service Configuration

### Step 7: Create Systemd Service

Systemd is Linux's service manager. It starts, stops, monitors, and auto-restarts your application.

```bash
cat > /etc/systemd/system/wikipedia-agent.service << 'EOF'
[Unit]
Description=Wikipedia Search Agent
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/home/appuser/Fetch_wiki
Environment="OPENAI_API_KEY=your-openai-api-key-here"
Environment="OPENAI_MODEL=gpt-5-nano"
ExecStart=/home/appuser/Fetch_wiki/venv/bin/python mcp_client.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**Service file sections explained:**

#### [Unit] Section
```ini
[Unit]
Description=Wikipedia Search Agent    # Human-readable name
After=network.target                   # Wait for network before starting
```

#### [Service] Section
```ini
[Service]
Type=simple                            # Basic foreground process
User=appuser                           # Run as this user (not root!)
WorkingDirectory=/home/appuser/...     # cd here before running
Environment="OPENAI_API_KEY=..."       # Set environment variables
ExecStart=/path/to/python script.py    # Command to run
Restart=always                         # Restart if it crashes
RestartSec=5                           # Wait 5 seconds before restart
```

#### [Install] Section
```ini
[Install]
WantedBy=multi-user.target             # Start on normal system boot
```

### Step 8: Enable and Start Service

```bash
systemctl daemon-reload          # Reload systemd after adding new service
systemctl enable wikipedia-agent # Start on boot
systemctl start wikipedia-agent  # Start now
```

---

## Nginx Reverse Proxy

### What is a Reverse Proxy?

```
┌──────────┐        ┌─────────┐        ┌──────────────┐
│  User    │───────▶│  nginx  │───────▶│  Your App    │
│ Browser  │ :80    │         │ :8000  │  (uvicorn)   │
└──────────┘        └─────────┘        └──────────────┘
```

**Benefits:**
- Handle SSL/HTTPS termination
- Serve static files efficiently
- Add security headers
- Load balance multiple app instances
- Handle thousands of connections

### Step 9: Configure Nginx

```bash
cat > /etc/nginx/sites-available/wikipedia-agent << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
EOF
```

**Configuration explained:**

| Directive | Purpose |
|-----------|---------|
| `listen 80` | Accept HTTP connections on port 80 |
| `listen [::]:80` | Also accept IPv6 connections |
| `server_name _` | Accept any domain/IP |
| `proxy_pass` | Forward requests to your app |
| `proxy_set_header Host` | Pass original Host header |
| `proxy_set_header X-Real-IP` | Pass client's real IP address |
| `proxy_read_timeout 300s` | Wait up to 5 min for AI responses |

### Step 10: Enable Site

```bash
rm -f /etc/nginx/sites-enabled/default    # Remove default site
ln -sf /etc/nginx/sites-available/wikipedia-agent /etc/nginx/sites-enabled/
systemctl restart nginx
```

**Nginx sites pattern:**
- Config files in `sites-available/` (all configs)
- Symlink to `sites-enabled/` to activate
- Easy to enable/disable without deleting

---

## SSL/HTTPS Setup

### Step 11: Get SSL Certificate (Optional)

If you have a domain pointing to your server:

```bash
certbot --nginx -d yourdomain.com
```

Certbot will:
1. Verify you own the domain
2. Get a free certificate from Let's Encrypt
3. Auto-configure nginx for HTTPS
4. Set up auto-renewal

**Without a domain (using IP):**
```bash
certbot --nginx -d YOUR_IP.nip.io
```

---

## Management Commands

### Service Control

```bash
# Check status
systemctl status wikipedia-agent

# Start/Stop/Restart
systemctl start wikipedia-agent
systemctl stop wikipedia-agent
systemctl restart wikipedia-agent

# View logs (live)
journalctl -u wikipedia-agent -f

# View last 100 log lines
journalctl -u wikipedia-agent -n 100 --no-pager
```

### Updating the Application

```bash
cd /home/appuser/Fetch_wiki
git pull origin main
systemctl restart wikipedia-agent
```

### Testing

```bash
# Test app directly
curl http://127.0.0.1:8000/health

# Test through nginx
curl http://localhost/health

# Expected response:
# {"status":"healthy","model":"gpt-5-nano"}
```

---

## Troubleshooting

### App Won't Start

```bash
# Check logs for errors
journalctl -u wikipedia-agent -n 50 --no-pager

# Common issues:
# 1. Missing OPENAI_API_KEY
# 2. Wrong Python path
# 3. Permission issues
```

### 502 Bad Gateway

```bash
# 1. Check if app is running
systemctl status wikipedia-agent

# 2. Check if app is listening
curl http://127.0.0.1:8000/health

# 3. Check nginx error log
tail -f /var/log/nginx/error.log
```

### Permission Denied

```bash
# Fix file ownership
chown -R appuser:appuser /home/appuser/Fetch_wiki

# Fix venv permissions
chmod -R 755 /home/appuser/Fetch_wiki/venv/bin/
```

---

## File Locations Reference

| What | Location |
|------|----------|
| Application code | `/home/appuser/Fetch_wiki/` |
| Python virtual environment | `/home/appuser/Fetch_wiki/venv/` |
| Systemd service file | `/etc/systemd/system/wikipedia-agent.service` |
| Nginx config | `/etc/nginx/sites-available/wikipedia-agent` |
| Nginx error log | `/var/log/nginx/error.log` |
| Nginx access log | `/var/log/nginx/access.log` |
| App logs | `journalctl -u wikipedia-agent` |

---

## Quick Reference Card

```bash
# Deploy updates
cd /home/appuser/Fetch_wiki && git pull && systemctl restart wikipedia-agent

# Check status
systemctl status wikipedia-agent

# View live logs
journalctl -u wikipedia-agent -f

# Test health
curl http://localhost/health
```
