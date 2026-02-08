# WSJ Client

A Docker-based torrent automation client that searches ThePirateBay and downloads content through your choice of 5 torrent clients, all protected by VPN with kill switch.

## Features

- **Multi-Client Support** - Choose from rTorrent, qBittorrent, Transmission, Deluge, or aria2
- **VPN Kill Switch** - All traffic routed through VPN (23 providers supported)
- **ThePirateBay Search** - Automatic torrent discovery with tracker list injection
- **Progress Monitoring** - Real-time download status tracking
- **Security Options** - Localhost binding or nginx reverse proxy with authentication
- **Full Docker Stack** - Complete orchestration with health checks

## Architecture

```
┌──────────┐     ┌────────┐     ┌─────────┐     ┌──────────────┐
│   wsj    │────>│ nginx  │────>│   vpn   │────>│   torrent    │
│ (search) │     │(proxy) │     │(gluetun)│     │   client     │
└──────────┘     └────────┘     └─────────┘     └──────────────┘
                                      │
                                      └─> Internet (via VPN only)
```

All torrent clients share the VPN network namespace. **If VPN fails, clients lose all connectivity** (kill switch protection).

## Supported Clients

| Client           | Protocol     | Web UI Port | RAM Usage | Best For            |
| ---------------- | ------------ | ----------- | --------- | ------------------- |
| **rTorrent**     | XML-RPC      | 80 (nginx)  | 50-100MB  | Low resources       |
| **qBittorrent**  | REST API     | 8080        | 150-300MB | Modern UI, features |
| **Transmission** | JSON-RPC     | 9091        | 50-150MB  | Simplicity          |
| **Deluge**       | JSON-RPC     | 8112        | 100-200MB | Plugins             |
| **aria2**        | JSON-RPC 2.0 | 6800        | 20-50MB   | Speed, efficiency   |

## Requirements

- Docker Engine 20.10+
- Docker Compose v2.0+
- Active VPN subscription (any of 23 supported providers)
- 1GB RAM minimum (2GB recommended for qBittorrent)
- Linux/macOS (Windows via WSL2)


## Quick Start

### 1. Clone and Configure

```bash
# HTTPS
git clone https://github.com/ryanvisil17/wsj-client.git

# SSH
git clone git@github.com:ryanvisil17/wsj-client.git

cd wsj-client
cp .env.example .env
```

### 2. Set VPN Credentials

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

### 3. Configure Nginx

**Option A: Basic setup (no authentication)**

The default `nginx/nginx.conf` works out of the box for rTorrent.

**Option B: With authentication (recommended)**

```bash
# Generate password file
docker run --rm httpd:alpine htpasswd -Bbn admin yourpassword > nginx/.htpasswd

# Edit nginx/nginx.conf and uncomment the auth lines:
auth_basic "Torrent Clients";
auth_basic_user_file /etc/nginx/.htpasswd;

# Mount password file in docker-compose.yml nginx service:
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf
  - ./nginx/.htpasswd:/etc/nginx/.htpasswd
```

### 4. Start Services

Start nginx, which will automatically start the torrent client and VPN (via `depends_on`):

```bash
docker compose up -d nginx

# Verify VPN connection (should show VPN IP, not your real IP)
docker compose exec vpn wget -qO- https://ipinfo.io/ip
```

### 5. Access Web UI

**Default (rTorrent):**

- http://localhost (via nginx reverse proxy)

**Other clients:**

- See [Web UI Access](#web-ui-access) section below

### 6. Run Torrent Downloads

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

## Switching Torrent Clients

To use a different torrent client, you must edit **three** configuration files:

### Step 1: Edit `.env`

```bash
# Change client selection
TORRENT_CLIENT=qbittorrent  # or transmission, deluge, aria2

# Change API endpoint URL (uncomment the correct one)
TORRENT_URL=http://vpn:8080  # qBittorrent
# TORRENT_URL=http://vpn:9091/transmission/rpc  # Transmission
# TORRENT_URL=http://vpn:8112  # Deluge
# TORRENT_URL=http://vpn:6800/jsonrpc  # aria2

# Set credentials for your chosen client
TORRENT_USER=admin
TORRENT_PASSWORD=yourpassword
```

### Step 2: Edit `docker-compose.yml`

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

### Step 3: Edit `nginx/nginx.conf`

Update the upstream and proxy_pass for your client:

```nginx
# Comment out current client
# upstream rtorrent {
#   server vpn:8000;
# }

# Uncomment your preferred client
upstream qbittorrent {
  server vpn:8080;
}

location / {
  proxy_pass http://qbittorrent;
  ...
}
```

### Step 4: Restart

```bash
docker compose down
docker compose up -d nginx
```

## Web UI Access

### Option 1: Nginx Reverse Proxy (Default)

All clients are accessible through nginx on port 80:

- **rTorrent**: http://localhost/
- **qBittorrent**: http://localhost/qbittorrent/
- **Transmission**: http://localhost/transmission/
- **Deluge**: http://localhost/deluge/
- **aria2**: http://localhost/aria2/

**Enable Authentication:**

```bash
# Generate password file
docker run --rm httpd:alpine htpasswd -Bbn admin yourpassword > nginx/.htpasswd

# Update docker-compose.yml to mount it
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf
  - ./nginx/.htpasswd:/etc/nginx/.htpasswd

# Edit nginx.conf and uncomment auth lines:
auth_basic "Torrent Clients";
auth_basic_user_file /etc/nginx/.htpasswd;
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

** Security:** Always bind to `127.0.0.1` for localhost-only access. Never expose ports as `8080:8080` without authentication.

## VPN Providers

23 VPN providers supported through [Gluetun](https://github.com/qdm12/gluetun):

**Popular choices:**

- **Mullvad** - Best privacy, no logs, €5/month → [`docs/mullvad-setup.md`](docs/mullvad-setup.md)
- **NordVPN** - Fast WireGuard, large network → [`docs/nordvpn-setup.md`](docs/nordvpn-setup.md)
- **Private Internet Access** - Port forwarding support → [`docs/pia-setup.md`](docs/pia-setup.md)
- **ProtonVPN** - Port forwarding, excellent privacy → [`docs/protonvpn-setup.md`](docs/protonvpn-setup.md)

**All supported:** AirVPN, Cyberghost, ExpressVPN, FastestVPN, HideMyAss, IPVanish, IVPN, Mullvad, NordVPN, Perfect Privacy, PIA, PrivateVPN, Privado, ProtonVPN, PureVPN, SlickVPN, Surfshark, TorGuard, VPN Secure, VPN Unlimited, VyprVPN, Windscribe, Custom

See [`docs/`](docs/) directory for detailed setup guides.

## Usage

### Via Docker Compose

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

### Standalone Script

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
└── clients/                 # Auto-created on first run
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

## Configuration Reference

### Environment Variables (`.env`)

```bash
# Torrent Client
TORRENT_CLIENT=rtorrent           # rtorrent | qbittorrent | transmission | deluge | aria2

# VPN Provider
VPN_SERVICE_PROVIDER=nordvpn      # See docs/ for your provider
VPN_TYPE=wireguard                # wireguard | openvpn
SERVER_COUNTRIES=United States
SERVER_CATEGORIES=P2P

# VPN Credentials (provider-specific)
NORDVPN_TOKEN=your_token
WIREGUARD_PRIVATE_KEY=your_key
# OR
OPENVPN_USER=your_username
OPENVPN_PASSWORD=your_password

# Client Credentials
RTORRENT_USER=admin               # For rTorrent
RTORRENT_PASSWORD=password
# OR
TORRENT_USER=admin                # For qBittorrent, Transmission, Deluge
TORRENT_PASSWORD=password
# OR
RPC_SECRET=your_secret            # For aria2

# System
PUID=1000                         # User ID (run: id -u)
PGID=1000                         # Group ID (run: id -g)
TZ=America/New_York

# Network
FIREWALL_OUTBOUND_SUBNETS=192.168.1.0/24
DNS_SERVER=on
DNS_UPSTREAM_RESOLVERS=cloudflare
```

## Troubleshooting

### VPN Not Connecting

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
# Check if client is running
docker compose ps

# Verify client is using VPN IP
docker compose exec torrent wget -qO- https://ipinfo.io/ip

# Check client logs
docker compose logs torrent

# Test connectivity from wsj container
docker compose exec wsj curl -v http://vpn:8080
```

### Download Stuck at 0%

```bash
# Verify VPN connectivity
docker compose exec vpn ping -c 3 8.8.8.8

# Check if kill switch is blocking (expected behavior if VPN down)
docker compose exec vpn iptables -L -n -v

# Restart entire stack
docker compose down
docker compose up -d nginx
```

### Permission Errors

```bash
# Fix ownership of client directories
sudo chown -R $USER:$USER clients/

# Verify PUID/PGID match your user
id -u  # Should match PUID in .env
id -g  # Should match PGID in .env
```

## Examples

### Download Today's Wall Street Journal

```bash
# Using current date
python main.py "Wall Street Journal $(date +%Y)" \
               "Wall Street Journal $(date +%A %B %-d, %Y)"
```

### Schedule Daily Downloads

```bash
# Add to crontab
crontab -e

# Download every day at 6 AM
0 6 * * * cd /path/to/wsj-client && docker compose up -d wsj >> /var/log/wsj-client.log 2>&1
```

### Switch to qBittorrent

```bash
# 1. Stop services
docker compose down

# 2. Edit .env
sed -i 's/TORRENT_CLIENT=.*/TORRENT_CLIENT=qbittorrent/' .env

# 3. Edit docker-compose.yml (comment rtorrent, uncomment qbittorrent)
# 4. Edit nginx/nginx.conf (comment rtorrent upstream, uncomment qbittorrent)

# 5. Start with new client
docker compose up -d nginx

# 6. Access at http://localhost:8080 (or http://localhost/qbittorrent/ via nginx)
```

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

3. **Enable HTTPS** with Let's Encrypt:

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

## Maintenance

### Update Containers

```bash
docker compose pull
docker compose up -d nginx --force-recreate
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f vpn

# Last 50 lines
docker compose logs --tail=50 wsj
```

### Backup Configuration

```bash
tar -czf wsj-client-backup.tar.gz .env docker-compose.yml nginx/
```

### Clean Downloads

```bash
# Remove all downloaded files
rm -rf clients/*/downloads/*
```

## License

MIT License - For personal and educational use only.
