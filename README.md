# WSJ Client

Automate torrent downloads from ThePirateBay with a single Docker command. Connects to your existing torrent client or deploy a complete VPN-protected stack.

---

## Table of Contents

- [Features](#features)
- [Quick Start (Existing Torrent Client)](#quick-start-existing-torrent-client)
- [Full Stack Setup (VPN + Torrent Client)](#full-stack-setup-vpn--torrent-client)
- [Supported Torrent Clients](#supported-torrent-clients)
- [Switching Torrent Clients](#switching-torrent-clients)
- [Web UI Access](#web-ui-access)
- [VPN Providers](#vpn-providers)
- [Usage Examples](#usage-examples)
- [Configuration Reference](#configuration-reference)
- [Directory Structure](#directory-structure)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)
- [Maintenance](#maintenance)

---

## Features

- **Single Command Deployment** - Already have a torrent client? Add automation with one Docker command
- **Multi-Client Support** - Works with rTorrent, qBittorrent, Transmission, Deluge, or aria2
- **ThePirateBay Search** - Automatic torrent discovery with tracker list injection
- **Progress Monitoring** - Real-time download status tracking
- **Optional VPN Stack** - Full Docker Compose setup with VPN kill switch (23 providers)
- **Security Options** - Localhost binding or nginx reverse proxy with authentication

---

## Quick Start (Existing Torrent Client)

**Already running qBittorrent, Transmission, or another torrent client?** Just add automatic search and download with one command.

### Prerequisites

- Docker installed
- Torrent client running on your machine (qBittorrent, Transmission, etc.)
- Know your torrent client's Web UI URL, username, and password

### Run Single Command

```bash
# qBittorrent example
docker run --rm \
  -e TORRENT_CLIENT=qbittorrent \
  -e TORRENT_URL=http://host.docker.internal:8080 \
  -e TORRENT_USER=admin \
  -e TORRENT_PASSWORD=adminpass \
  ryanvisil17/wsj-client \
  "Wall Street Journal 2026" \
  "Wall Street Journal Saturday February 7, 2026"

# Transmission example
docker run --rm \
  -e TORRENT_CLIENT=transmission \
  -e TORRENT_URL=http://host.docker.internal:9091/transmission/rpc \
  -e TORRENT_USER=transmission \
  -e TORRENT_PASSWORD=transmission \
  ryanvisil17/wsj-client \
  "Wall Street Journal 2026" \
  "Wall Street Journal Saturday February 7, 2026"

# rTorrent example
docker run --rm \
  -e TORRENT_CLIENT=rtorrent \
  -e TORRENT_URL=http://host.docker.internal:8080/plugins/httprpc/action.php \
  -e TORRENT_USER=admin \
  -e TORRENT_PASSWORD=password \
  ryanvisil17/wsj-client \
  "Wall Street Journal 2026" \
  "Wall Street Journal Saturday February 7, 2026"
```

**That's it!** The script will:

1. Search ThePirateBay for your query
2. Find the exact torrent name match
3. Add it to your running torrent client
4. Monitor download progress
5. Exit when complete

### Environment Variables

| Variable           | Description                 | Example                                   |
| ------------------ | --------------------------- | ----------------------------------------- |
| `TORRENT_CLIENT`   | Client type                 | `qbittorrent`, `transmission`, `rtorrent` |
| `TORRENT_URL`      | Web UI or API endpoint      | `http://localhost:8080`                   |
| `TORRENT_USER`     | Username for authentication | `admin`                                   |
| `TORRENT_PASSWORD` | Password for authentication | `yourpassword`                            |

**Note:** Windows users need Docker Desktop or Docker Engine backend, or run from Powershell directly.

---

## Full Stack Setup (VPN + Torrent Client)

Want a complete solution with VPN protection and torrent client included? Deploy the full stack with Docker Compose.

### Architecture

```
┌──────────┐     ┌────────┐     ┌─────────┐     ┌──────────────┐
│   wsj    │────>│ nginx  │────>│   vpn   │────>│   torrent    │
│ (search) │     │(proxy) │     │(gluetun)│     │   client     │
└──────────┘     └────────┘     └─────────┘     └──────────────┘
                                      │
                                      └─> Internet (via VPN only)
```

All torrent clients share the VPN network namespace. **If VPN fails, clients lose all connectivity** (kill switch protection).

### Requirements

- Docker Engine 20.10+
- Docker Compose v2.0+
- Active VPN subscription (any of 23 supported providers)
- 1GB RAM minimum (2GB recommended for qBittorrent)
- Linux/macOS (Windows via WSL2)

### Setup Steps

#### 1. Clone and Configure

```bash
# HTTPS
git clone https://github.com/ryanvisil17/wsj-client.git

# SSH
git clone git@github.com:ryanvisil17/wsj-client.git

cd wsj-client
cp .env.example .env
```

#### 2. Set VPN Credentials

Edit `.env` with your VPN provider credentials:

```bash
# Example: NordVPN
VPN_SERVICE_PROVIDER=nordvpn
VPN_TYPE=wireguard
NORDVPN_TOKEN=your_token_here
WIREGUARD_PRIVATE_KEY=your_key_here

# System
PUID=1000
PGID=1000
TZ=America/New_York
```

See [`docs/`](docs/) directory for your provider's setup guide (23 providers supported).

#### 3. Configure Nginx (Optional)

**Option A: Basic setup (no authentication)**

The default `nginx/nginx.conf` works out of the box for rTorrent.

**Option B: With authentication (recommended)**

```bash
# Generate password file
docker run --rm httpd:alpine htpasswd -Bbn admin yourpassword > nginx/.htpasswd

# Edit nginx/nginx.conf and uncomment the auth lines (around line 56-57):
# auth_basic "Torrent Clients";
# auth_basic_user_file /etc/nginx/.htpasswd;

# Add .htpasswd volume mount in docker-compose.yml nginx service:
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf
  - ./nginx/.htpasswd:/etc/nginx/.htpasswd  # Add this line

# Restart nginx
docker compose restart nginx
```

#### 4. Start Services

Start nginx, which will automatically start the torrent client and VPN (via `depends_on`):

```bash
docker compose up -d nginx

# Verify VPN connection (should show VPN IP, not your real IP)
docker compose exec vpn wget -qO- https://ipinfo.io/ip
```

#### 5. Access Web UI

**Default (rTorrent):**

- http://localhost (via nginx reverse proxy)

**Other clients:**

- See [Web UI Access](#web-ui-access) section below

#### 6. Run Torrent Downloads

The `wsj` service runs separately to download torrents:

```bash
# Edit command in docker-compose.yml first:
services:
  wsj:
    command: ["Wall Street Journal 2026", "Wall Street Journal Saturday February 7, 2026"]

# Then run the wsj service
docker compose up -d wsj
docker compose logs wsj -f
```

---

## Supported Torrent Clients

| Client           | Protocol     | Internal Port | RAM Usage | Best For            | API Endpoint (Single Command)                      |
| ---------------- | ------------ | ------------- | --------- | ------------------- | -------------------------------------------------- |
| **rTorrent**     | XML-RPC      | 8080          | 50-100MB  | Low resources       | `http://localhost:8080/plugins/httprpc/action.php` |
| **qBittorrent**  | REST API     | 8080          | 150-300MB | Modern UI, features | `http://localhost:8080`                            |
| **Transmission** | JSON-RPC     | 9091          | 50-150MB  | Simplicity          | `http://localhost:9091/transmission/rpc`           |
| **Deluge**       | JSON-RPC     | 8112          | 100-200MB | Plugins             | `http://localhost:8112/json`                       |
| **aria2**        | JSON-RPC 2.0 | 6800          | 20-50MB   | Speed, efficiency   | `http://localhost:6800/jsonrpc`                    |

**Notes:**
- **Internal Port**: Port the client uses inside its container
- **API Endpoint**: For single command usage with existing clients on localhost
- **Docker Compose**: All clients accessed via nginx at http://localhost/ or via VPN container ports
- **For Docker Compose URLs**: Replace `localhost` with `vpn` (e.g., `http://vpn:8080`)

---

## Switching Torrent Clients

### For Docker Compose Stack

To use a different torrent client in the full stack, edit **three** configuration files:

#### Step 1: Edit `.env`

```bash
# Change client selection
TORRENT_CLIENT=qbittorrent  # or transmission, deluge, aria2

# Change API endpoint URL (uncomment the correct one)
TORRENT_URL=http://vpn:8080  # qBittorrent
# TORRENT_URL=http://vpn:9091/transmission/rpc  # Transmission
# TORRENT_URL=http://vpn:8112/json  # Deluge
# TORRENT_URL=http://vpn:6800/jsonrpc  # aria2

# Set credentials for your chosen client
TORRENT_USER=admin
TORRENT_PASSWORD=yourpassword
```

#### Step 2: Edit `docker-compose.yml`

Comment out the current client and uncomment your preferred one. All clients use the service name `torrent`:

```yaml
# Comment out current client
# torrent:
#   container_name: rtorrent
#   image: crazymax/rtorrent-rutorrent:latest
#   ...

# Uncomment your preferred client
torrent:
  container_name: qbittorrent
  image: lscr.io/linuxserver/qbittorrent:latest
  ...
```

#### Step 3: Edit `nginx/nginx.conf`

Comment out the current client's location block and uncomment your preferred client:

```nginx
# Comment out rTorrent location block (lines 67-80)
# location / {
#   proxy_pass http://vpn:8080/;
#   ...
# }
#
# location /RPC2 {
#   include scgi_params;
#   scgi_pass vpn:18000;
#   ...
# }

# Uncomment qBittorrent location block (lines 86-89)
location / {
  proxy_pass http://vpn:8080/;
  proxy_http_version 1.1;
}
```

**Note:** Only ONE client can be active at a time since they all serve at the root path `/`.

#### Step 4: Restart

```bash
docker compose down
docker compose up -d nginx
```

### For Single Docker Command

Just change the environment variables:

```bash
docker run --rm \
  --network host \
  -e TORRENT_CLIENT=transmission \
  -e TORRENT_URL=http://localhost:9091/transmission/rpc \
  -e TORRENT_USER=transmission \
  -e TORRENT_PASSWORD=transmission \
  ryanvisil17/wsj-client \
  "Your Search Query" \
  "Exact Torrent Name"
```

---

## Web UI Access

### Option 1: Nginx Reverse Proxy (Default for Docker Compose)

The active torrent client is accessible through nginx on port 80:

- **Any Active Client**: http://localhost/

**Note:** Only one client can be active at a time through nginx since all clients serve at the root path. The active client is determined by which service is uncommented in both `docker-compose.yml` and `nginx/nginx.conf`.

**Enable Authentication:**

```bash
# Generate password file
docker run --rm httpd:alpine htpasswd -Bbn admin yourpassword > nginx/.htpasswd

# The password file is already mounted in docker-compose.yml
# Just uncomment the auth lines in nginx/nginx.conf:
auth_basic "Torrent Clients";
auth_basic_user_file /etc/nginx/.htpasswd;

# Restart nginx
docker compose restart nginx
```

### Option 2: Direct Port Access (Localhost Only)

For local-only access without nginx, uncomment in `docker-compose.yml`:

```yaml
vpn:
  ports:
    - 127.0.0.1:8080:8080 # qBittorrent
    # - 127.0.0.1:9091:9091  # Transmission
    # - 127.0.0.1:8112:8112  # Deluge
    # - 127.0.0.1:6800:6800  # aria2
```

**Security Warning:** Always bind to `127.0.0.1` for localhost-only access. Never expose ports as `8080:8080` without authentication.

---

## VPN Providers

23 VPN providers supported through [Gluetun](https://github.com/qdm12/gluetun):

**Popular choices:**

- **Mullvad** - Best privacy, no logs, €5/month → [`docs/mullvad-setup.md`](docs/mullvad-setup.md)
- **NordVPN** - Fast WireGuard, large network → [`docs/nordvpn-setup.md`](docs/nordvpn-setup.md)
- **Private Internet Access** - Port forwarding support → [`docs/pia-setup.md`](docs/pia-setup.md)
- **ProtonVPN** - Port forwarding, excellent privacy → [`docs/protonvpn-setup.md`](docs/protonvpn-setup.md)

**All supported:** AirVPN, Cyberghost, ExpressVPN, FastestVPN, HideMyAss, IPVanish, IVPN, Mullvad, NordVPN, Perfect Privacy, PIA, PrivateVPN, Privado, ProtonVPN, PureVPN, SlickVPN, Surfshark, TorGuard, VPN Secure, VPN Unlimited, VyprVPN, Windscribe, Custom

See [`docs/`](docs/) directory for detailed setup guides.

---

## Usage Examples

### Single Docker Command with Existing Client

```bash
# Download today's Wall Street Journal
docker run --rm \
  --network host \
  -e TORRENT_CLIENT=qbittorrent \
  -e TORRENT_URL=http://localhost:8080 \
  -e TORRENT_USER=admin \
  -e TORRENT_PASSWORD=adminpass \
  ryanvisil17/wsj-client \
  "Wall Street Journal $(date +%Y)" \
  "Wall Street Journal $(date +%A %B %-d, %Y)"
```

### Docker Compose Stack

Edit the command in `docker-compose.yml`:

```yaml
services:
  wsj:
    command:
      [
        "Wall Street Journal 2026",
        "Wall Street Journal Saturday February 7, 2026",
      ]
```

Then run:

```bash
docker compose up -d wsj
docker compose logs wsj -f
```

### Standalone Python Script

```bash
python main.py "Search Query" "Exact Torrent Name"
```

**Options:**

```bash
python main.py --help

Arguments:
  query                  Search term for TPB API
  exact_name            Exact torrent name to match (optional)

Options:
  --torrent-url         Backend URL (default: from env)
  --torrent-user        Username for authentication
  --torrent-password    Password for authentication
  --poll-interval       Status check interval in seconds (default: 10)
  --timeout             Download timeout in seconds (default: 3600)
```

### Schedule Daily Downloads

```bash
# Add to crontab
crontab -e

# Download every day at 6 AM using single command
0 6 * * * docker run --rm --network host -e TORRENT_CLIENT=qbittorrent -e TORRENT_URL=http://localhost:8080 -e TORRENT_USER=admin -e TORRENT_PASSWORD=pass ryanvisil17/wsj-client "WSJ $(date +%Y)" "WSJ $(date +%A %B %-d, %Y)" >> /var/log/wsj.log 2>&1

# OR with docker compose
0 6 * * * cd /path/to/wsj-client && docker compose up -d wsj >> /var/log/wsj-client.log 2>&1
```

---

## Configuration Reference

### Environment Variables

```bash
# Client Selection
TORRENT_CLIENT=rtorrent           # rtorrent | qbittorrent | transmission | deluge | aria2

# API Endpoints (choose one matching your client)
TORRENT_URL=http://vpn:8080/plugins/httprpc/action.php  # rTorrent
# TORRENT_URL=http://vpn:8080                            # qBittorrent
# TORRENT_URL=http://vpn:9091/transmission/rpc           # Transmission
# TORRENT_URL=http://vpn:8112/json                       # Deluge
# TORRENT_URL=http://vpn:6800/jsonrpc                    # aria2

# Client Credentials
TORRENT_USER=admin
TORRENT_PASSWORD=password

# System (for Docker Compose stack)
PUID=1000                         # User ID (run: id -u)
PGID=1000                         # Group ID (run: id -g)
TZ=America/New_York

# VPN Provider (for Docker Compose stack)
VPN_SERVICE_PROVIDER=nordvpn      # See docs/ for your provider
VPN_TYPE=wireguard                # wireguard | openvpn
SERVER_COUNTRIES=United States
SERVER_CATEGORIES=P2P

# VPN Credentials (provider-specific, see docs/)
NORDVPN_TOKEN=your_token
WIREGUARD_PRIVATE_KEY=your_key
# OR
OPENVPN_USER=your_username
OPENVPN_PASSWORD=your_password

# Network (for Docker Compose stack)
FIREWALL_OUTBOUND_SUBNETS=192.168.1.0/24
DNS_SERVER=on
DNS_UPSTREAM_RESOLVERS=cloudflare
```

---

## Directory Structure

```
wsj-client/
├── main.py                  # Multi-client torrent automation
├── Dockerfile               # Python client container
├── docker-compose.yml       # Full stack orchestration
├── .env                     # Your configuration (gitignored)
├── .env.example             # Configuration template
├── requirements.txt         # Python dependencies
├── nginx/
│   ├── nginx.conf           # Reverse proxy configuration
│   └── .htpasswd            # HTTP Basic Auth (if enabled)
├── docs/                    # VPN provider setup guides (23 providers)
│   ├── nordvpn-setup.md
│   ├── mullvad-setup.md
│   └── ...
└── clients/                 # Auto-created on first run (Docker Compose only)
    ├── rtorrent/
    │   ├── data/
    │   ├── downloads/
    │   └── passwd/
    ├── qbittorrent/
    │   ├── config/
    │   └── downloads/
    ├── transmission/
    │   ├── config/
    │   ├── downloads/
    │   └── watch/
    ├── deluge/
    │   ├── config/
    │   └── downloads/
    └── aria2/
        ├── config/
        └── downloads/
```

---

## Troubleshooting

### VPN Not Connecting (Docker Compose Only)

```bash
# Check VPN logs
docker compose logs vpn

# Verify credentials in .env
cat .env | grep -E "VPN_|TOKEN|PRIVATE_KEY"

# Test DNS resolution
docker compose exec vpn nslookup google.com

# Restart VPN container
docker compose restart vpn
```

### Torrent Client Not Accessible

```bash
# For Docker Compose stack
docker compose ps
docker compose exec torrent wget -qO- https://ipinfo.io/ip
docker compose logs torrent

# For single command (check your local torrent client)
# Make sure qBittorrent/Transmission is running
# Verify Web UI is accessible: http://localhost:8080
```

### Connection Errors with Single Command

```bash
# Verify your torrent client is running
curl http://localhost:8080  # qBittorrent
curl http://localhost:9091  # Transmission

# Check credentials
# qBittorrent: Tools -> Options -> Web UI
# Transmission: settings.json

# Test with --network host
docker run --rm --network host -e ... ryanvisil17/wsj-client ...

# Windows: Ensure Docker Desktop is using WSL2 backend
```

### Download Stuck at 0%

```bash
# For Docker Compose stack
docker compose exec vpn ping -c 3 8.8.8.8
docker compose exec vpn iptables -L -n -v
docker compose down
docker compose up -d nginx

# For single command
# Check your torrent client's connection status
# Ensure torrents are actually downloading in the client
```

### Permission Errors (Docker Compose Only)

```bash
# Fix ownership of client directories
sudo chown -R $USER:$USER clients/

# Verify PUID/PGID match your user
id -u  # Should match PUID in .env
id -g  # Should match PGID in .env
```

---

## Security Best Practices

1. **Change default passwords** immediately:
   - qBittorrent: Change on first login (default: admin/adminpass)
   - Transmission: Edit `settings.json` in config directory
   - Deluge: Change from default "deluge"
   - aria2: Set strong `RPC_SECRET` in `.env`

2. **Use strong passwords**:

   ```bash
   openssl rand -base64 32
   ```

3. **Enable HTTPS** with Let's Encrypt (Docker Compose only):

   ```bash
   sudo certbot certonly --standalone -d yourdomain.com
   # Then configure nginx with SSL certificates
   ```

4. **Restrict access by IP** in `nginx/nginx.conf`:

   ```nginx
   location / {
     allow 192.168.1.0/24;  # Your local network
     deny all;
     proxy_pass http://vpn:8080;
   }
   ```

5. **Never expose ports without** `127.0.0.1` binding unless using nginx with authentication

6. **Single command users**: Don't expose your torrent client to the internet without authentication

---

## Maintenance

### Update Docker Image

```bash
# Pull latest image
docker pull ryanvisil17/wsj-client:latest

# For Docker Compose stack
docker compose pull
docker compose up -d nginx --force-recreate
```

### View Logs

```bash
# Single command (runs in foreground by default)
docker run --rm ... ryanvisil17/wsj-client ...

# Docker Compose
docker compose logs -f
docker compose logs -f vpn
docker compose logs --tail=50 wsj
```

### Backup Configuration

```bash
tar -czf wsj-client-backup.tar.gz .env docker-compose.yml nginx/
```

### Clean Downloads

```bash
# Docker Compose
rm -rf clients/*/downloads/*

# Single command (clean your torrent client's download folder)
```

---

## License

MIT License - For personal and educational use only.

## Disclaimer

This tool is for downloading legally available content only. Users are responsible for complying with their local laws and the terms of service of their VPN provider. The authors assume no liability for misuse.
