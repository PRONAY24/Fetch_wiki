# 🏗️ Architecture & Hosting Flow Explained

This guide explains how your Wikipedia Search Agent application is hosted, how traffic flows from a user to your server, and how the magical conversion from HTTP to HTTPS happens.

## 🗺️ High-Level Overview

Imagine your application hosting as a restaurant:
- **Linode VM**: The building.
- **IP Address**: The street address.
- **Domain Name**: The name on the sign (easier to remember than the address).
- **Nginx**: The Host/Maitre d' at the front door.
- **Gunicorn/Uvicorn**: The Waiters.
- **FastAPI/Python App**: The Chef cooking the answers.

### The Architecture Diagram

```mermaid
graph TD
    User[👤 User Browser] -->|HTTPS Request| DNS[🌐 DNS System]
    DNS -->|Resolves Domain to IP| Nginx[🛡️ Nginx Web Server]
    
    subgraph "Linode Virtual Machine"
        Nginx -->|Reverse Proxy (Internally)| Gunicorn[🦄 Gunicorn Process Manager]
        Gunicorn -->|Manages Workers| Uvicorn[⚡ Uvicorn Worker]
        Uvicorn -->|Runs| FastAPI[🐍 FastAPI App]
        
        subgraph "Application Logic"
            FastAPI -->|Orchestrates| LangGraph[🤖 LangGraph Agent]
            LangGraph -->|Calls Tools| MCPServer[🛠️ MCP Server]
            MCPServer -->|Fetches| Wikipedia[📚 Wikipedia API]
        end
    end
```

---

## 🔄 The Journey of a Request

Here is exactly what happens when someone types your URL:

1.  **DNS Resolution**:
    - User types `https://wiki.yourdomain.com`.
    - Their computer asks a DNS server: "Where is wiki.yourdomain.com?"
    - DNS server replies with your Linode VM's IP address (e.g., `172.104.x.x`).

2.  **Connection (The Handshake)**:
    - The browser sends a request to that IP on **Port 443** (the standard HTTPS port).
    - **Nginx** picks up this request.

3.  **SSL/TLS Termination (HTTP → HTTPS)**:
    - This is where the security happens. Nginx holds your **SSL Certificate**.
    - Nginx decrypts the incoming secure message.
    - Inside the server, the message is now plain text (safe because it's inside your private machine).

4.  **Reverse Proxy**:
    - Nginx looks at its rules: "Oh, traffic for this domain goes to `127.0.0.1:8000`".
    - It forwards the request to port 8000 on the same machine.
    - This is called **Reverse Proxying**—Nginx acts on behalf of the backend.

5.  **Application Processing**:
    - **Gunicorn** (listening on 8000) grabs the request.
    - It hands it to a **Uvicorn** worker (which speaks the ASGI language FastAPI understands).
    - **FastAPI** executes your Python code (`chat` function).
    - Your code performs the search, maybe asks the LLM, and creates a response.

6.  **The Return Trip**:
    - Python returns the answer to Uvicorn -> Gunicorn -> Nginx.
    - Nginx **encrypts** the response again (HTTPS).
    - Nginx sends it back across the internet to the user.

---

## 🔒 Understanding HTTPS (The Security Layer)

You asked: *"How does it get converted into HTTPS from HTTP?"*

### 1. HTTP vs HTTPS
- **HTTP**: like sending a postcard. Anyone handling the mail (routers, ISPs, hackers on Wi-Fi) can read it.
- **HTTPS**: like sending a locked armored box. Only the sender and receiver have the keys.

### 2. How we got the Lock (SSL Certificate)
In your `deploy.sh`, you see this command:
```bash
certbot --nginx -d yourdomain.com
```

Here is what **Certbot** did:
1.  **Talked to Let's Encrypt**: "Hi, this server claims to be `yourdomain.com`. Can I have a certificate?"
2.  **The Challenge**: Let's Encrypt said, "Prove it. Put this secret file on your web server."
3.  **Verification**: Certbot configured Nginx to serve that secret file. Let's Encrypt checked it remotely. "Okay, you control the server."
4.  **Issuance**: Let's Encrypt gave you a **Certificate** (Public Key) and a **Private Key**.
5.  **Configuration**: Certbot edited your Nginx config to say:
    - "Listen on port 443 (HTTPS)."
    - "Use these key files to encrypt traffic."
    - "If anyone calls on port 80 (HTTP), tell them nothing is here and redirect them to HTTPS."

### 3. The "Conversion"
It's not really converting the data *on the fly* in a magical way; it's **wrapping** it.
- **Nginx** wraps your data in an encrypted SSL layer before it leaves the server.
- **Nginx** unwraps incoming data before handing it to Python.
- Your Python app usually doesn't even know it's HTTPS; it just sees requests coming from Nginx.

---

## 🛠️ Components of Your Setup

### 1. Linode (The Cloud Provider)
Provides the raw "virtual metal" (CPU, RAM, Disk) and the Public IP address.

### 2. Nginx (The Web Server)
Fast, secure, and rugged. It handles the "dirty work" of the internet:
- SSL Encryption/Decryption.
- Slow client connections.
- Static file serving (images, CSS).
- preventing your Python app from being overwhelmed by opening too many connections.

### 3. Gunicorn & Uvicorn (The App Servers)
- **FastAPI** is your code frameowrk.
- **Uvicorn** is the engine that runs FastAPI (it speaks "Async").
- **Gunicorn** is the manager. It spawns multiple "workers" (copies of Uvicorn). If one crashes, Gunicorn restarts it. If you have 2 CPU cores, Gunicorn can run 5 workers to handle more traffic at once.

---

## 🎓 How to Teach This Flow

To explain this to someone else, use the **"Office Receptionist"** analogy:

1.  **The Internet** is the street outside.
2.  **Nginx** is the **Receptionist** at the front desk.
    - She checks IDs (SSL).
    - She stops spammers (Firewall/Security).
    - She directs legitimate visitors to the right office.
3.  **The Python App** is the **Specialist** inside the back office.
    - They don't want to deal with checking IDs or giving directions.
    - They just want to do the work (Search Wikipedia).
4.  **Gunicorn** is the **Office Manager**.
    - Ensures the Specialist is at their desk.
    - Hires more Specialists (workers) if the line gets long.

This separation of duties makes your app **secure**, **scalable**, and **robust**.
