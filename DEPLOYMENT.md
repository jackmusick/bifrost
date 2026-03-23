# Bifrost Deployment Guide

This guide walks you through deploying Bifrost on your own hardware today, and describes a clear path to promoting that deployment to Azure when you're ready.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Software Prerequisites](#2-software-prerequisites)
3. [Architecture Overview](#3-architecture-overview)
4. [Self-Hosted Deployment (Step-by-Step)](#4-self-hosted-deployment-step-by-step)
5. [Networking Requirements](#5-networking-requirements)
6. [Security Hardening](#6-security-hardening)
7. [Day-2 Operations (Backups, Scaling, Updates)](#7-day-2-operations)
8. [Promoting to Azure Production](#8-promoting-to-azure-production)
9. [Sample Workflows (Bootstrapping)](#9-sample-workflows-bootstrapping)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. System Requirements

### Recommended Hardware (Self-Hosted)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 8 GB | 16–32 GB |
| **Disk (OS + Docker)** | 40 GB SSD | 100 GB SSD |
| **Disk (data volumes)** | 20 GB | 100+ GB (grows with workflows & files) |
| **Network** | 100 Mbps | 1 Gbps |

> **Why these specs?** Bifrost runs 10+ Docker containers concurrently (API, database, cache, message queue, object storage, scheduler, worker, etc.). PostgreSQL and the worker processes are the most memory-hungry services. The recommendations above give comfortable headroom for multiple concurrent automation workflows plus storage for workspace files.

### Operating System

Any modern Linux distribution works. Tested and recommended:

- **Ubuntu 22.04 LTS** or **24.04 LTS** (easiest Docker experience)
- **Debian 12**
- **Rocky Linux 9** / **AlmaLinux 9** (RHEL-compatible)
- **Windows Server 2022** with WSL 2 + Docker Desktop (functional but not recommended for production)

> macOS is supported for local development only—not recommended for production self-hosting.

---

## 2. Software Prerequisites

You need **Docker Engine** and **Docker Compose** (v2). Nothing else needs to be installed on the host.

### Install Docker (Ubuntu / Debian)

```bash
# Remove any old Docker versions
sudo apt-get remove -y docker docker-engine docker.io containerd runc

# Install dependencies
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's GPG key and repository
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine and Compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow your user to run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version          # e.g. Docker version 26.x.x
docker compose version    # e.g. Docker Compose version v2.x.x
```

### Install Docker (Rocky / AlmaLinux / RHEL)

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

### Additional tools (optional but useful)

```bash
# git — to clone the repository
sudo apt-get install -y git

# openssl — used by setup.sh to generate secrets
sudo apt-get install -y openssl
```

---

## 3. Architecture Overview

```
Internet / Internal Users
         │
         ▼
  ┌─────────────────────────────────────────┐
  │  Reverse Proxy (Nginx in Client image)  │
  │  Handles TLS termination (port 443)     │
  └────────────────┬────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │  FastAPI (API svc) │  ← REST + WebSocket + MCP
         └────┬────┬────┬─────┘
              │    │    │
    ┌─────────▼┐ ┌─▼──────┐ ┌▼──────────┐ ┌──────────┐
    │PostgreSQL│ │RabbitMQ│ │  Redis     │ │  MinIO   │
    │(pgvector)│ │(queue) │ │(cache/sess)│ │(S3 store)│
    └──────────┘ └───┬────┘ └───────────┘ └──────────┘
                     │
          ┌──────────▼──────────┐
          │  Worker(s)          │  ← horizontally scalable
          │  (workflow executor)│
          └─────────────────────┘
          ┌─────────────────────┐
          │  Scheduler          │  ← single instance (cron / OAuth refresh)
          └─────────────────────┘
```

**What each service does:**

| Service | Image | Role |
|---------|-------|------|
| `client` | nginx + React | Serves the web UI and proxies API requests |
| `api` | FastAPI / Uvicorn | REST API, WebSockets, authentication |
| `postgres` | pgvector/pgvector:pg16 | Primary database with vector-search extension |
| `pgbouncer` | pgbouncer | Database connection pooler (protects Postgres) |
| `rabbitmq` | rabbitmq:3.13 | Job queue for async workflow execution |
| `redis` | redis:7 | Session storage, module cache |
| `minio` | minio | S3-compatible object storage for workspace files |
| `scheduler` | (same as api) | Cron jobs, OAuth token refresh — **must run as a single instance** |
| `worker` | (same as api) | Executes workflow jobs from the queue — horizontally scalable |
| `init` | (same as api) | One-shot container that runs database migrations on startup |

---

## 4. Self-Hosted Deployment (Step-by-Step)

### Step 1 — Clone the repository

```bash
git clone https://github.com/MTG-Thomas/bifrost.git
cd bifrost
```

### Step 2 — Generate your configuration

Run the interactive setup script. It generates secure random secrets and creates your `.env` file:

```bash
./setup.sh
```

You will be prompted for:

- **Domain** — Enter `localhost` if you are testing locally with no public DNS yet.  
  Enter your real domain (e.g. `bifrost.example.com`) if you have DNS pointing at this machine.

The script automatically:
- Generates strong random passwords for PostgreSQL, RabbitMQ, MinIO, and the application secret key
- Configures WebAuthn (passkey) settings based on your domain
- Sets `BIFROST_ENVIRONMENT=production` for non-localhost deployments

After running the script, open `.env` and review a few settings:

```bash
# Open the generated .env file
nano .env   # or vim .env, or any editor you prefer
```

Key variables to verify:

```dotenv
# Should be your actual domain (or localhost for testing)
BIFROST_PUBLIC_URL=https://bifrost.example.com
BIFROST_WEBAUTHN_RP_ID=bifrost.example.com
BIFROST_WEBAUTHN_ORIGIN=https://bifrost.example.com

# Max parallel workflow jobs per worker (tune to your hardware)
BIFROST_MAX_CONCURRENCY=10

# Optional: create an initial admin account automatically on first boot
BIFROST_DEFAULT_USER_EMAIL=admin@example.com
BIFROST_DEFAULT_USER_PASSWORD=<strong-password>
```

### Step 3 — Start Bifrost

```bash
docker compose up -d
```

Docker will pull the required images (~1–2 GB total) and start all services. On first launch the `init` container runs database migrations — this takes about 30 seconds.

Watch the startup progress:

```bash
docker compose logs -f init   # wait for "migrations complete"
docker compose logs -f api    # wait for "Application startup complete"
```

### Step 4 — Verify everything is running

```bash
docker compose ps
```

All services should show `healthy` or `running`. Expected output (abbreviated):

```
NAME             IMAGE                    STATUS
bifrost-api      bifrost-api:latest       Up (healthy)
bifrost-client   bifrost-client:latest    Up
bifrost-postgres pgvector/pgvector:pg16   Up (healthy)
bifrost-pgbouncer edoburu/pgbouncer       Up (healthy)
bifrost-rabbitmq rabbitmq:3.13-mgmt       Up (healthy)
bifrost-redis    redis:7-alpine           Up (healthy)
bifrost-minio    minio/minio:latest       Up (healthy)
bifrost-scheduler bifrost-api:latest      Up
bifrost-worker   bifrost-api:latest       Up
```

### Step 5 — Open the web UI

- **HTTP (no TLS, local testing):** `http://localhost:80`  
  The Nginx container in the `client` service listens on port 80.

> If you mapped a different host port in `docker-compose.yml`, use that port instead.

Log in with your admin credentials. If you set `BIFROST_DEFAULT_USER_EMAIL` and `BIFROST_DEFAULT_USER_PASSWORD`, use those. Otherwise, use the registration flow to create your first user.

### Step 6 — (Recommended) Put Bifrost behind a TLS reverse proxy

For any machine reachable over a network—even internally—you should terminate HTTPS at a reverse proxy. See [Networking Requirements](#5-networking-requirements) for options.

---

## 5. Networking Requirements

### Do you need to open inbound ports from the WAN?

**For an initial lab deployment the answer is: almost certainly not.**

Bifrost is primarily an *outbound* system — it reaches out to third-party APIs, runs your Python workflows, and connects to services on your behalf. Users on your LAN access the web UI by connecting to the Bifrost host on port 80/443. None of that requires a WAN pinhole.

The one scenario that requires inbound internet access is **webhook-triggered automations**, where an external service (GitHub, Microsoft Graph, a PSA platform, etc.) needs to call Bifrost to fire a workflow. The webhook receiver endpoint is:

```
POST /api/hooks/{source_id}
```

These endpoints are unauthenticated in the traditional sense (no API key or session token required), but they are secured through two layers: HMAC signature validation performed by the adapter for each external service (the actual authentication mechanism), plus a UUID-based path that is unique per event source and not guessable (obscurity as a secondary defense). They are called by external services, so they must be reachable from the internet.

**Decision guide:**

| Use case | Inbound WAN port needed? |
|----------|--------------------------|
| Manual workflow execution from browser | ❌ No |
| Scheduled (cron) workflows | ❌ No |
| Workflows triggered by your own scripts or API calls | ❌ No — LAN access is sufficient |
| OAuth SSO (users log in via Google / Microsoft / etc.) | ✅ Yes — the OAuth callback URL (`/auth/callback`) must be reachable by the identity provider |
| Webhook-triggered workflows (GitHub events, Microsoft Graph subscriptions, etc.) | ✅ Yes — `/api/hooks/{source_id}` must be reachable from the internet |
| MCP server for external LLM clients (Claude Desktop, etc.) | ✅ Yes — `/mcp` and the OAuth endpoints must be reachable |

**For your initial lab:** Configure your LAN firewall to allow LAN clients on port 80/443. Skip the WAN pinhole entirely until you start building webhook-driven automations.

When you do need inbound webhook access, the cleanest options are:
- Open port 443 through your WAN and forward it to the Bifrost host (a single port-forward rule)
- Use a tunnel service like [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) or [ngrok](https://ngrok.com/) to expose the single HTTPS endpoint without touching your firewall — useful during development

### Ports used by Bifrost containers

| Port | Protocol | Service | Exposed to host? |
|------|----------|---------|-----------------|
| 80 | TCP | `client` (Nginx) | **Yes** — main entry point |
| 8000 | TCP | `api` | No (internal only) |
| 5432 | TCP | `postgres` | No (internal only) |
| 6432 | TCP | `pgbouncer` | No (internal only) |
| 5672 | TCP | `rabbitmq` | No (internal only) |
| 15672 | TCP | `rabbitmq` management UI | No (internal only) |
| 6379 | TCP | `redis` | No (internal only) |
| 9000 | TCP | `minio` S3 API | No (internal only)* |
| 9001 | TCP | `minio` console | No (internal only) |

> *MinIO's S3 API port (9000) must be reachable by users' browsers if they upload/download large files directly (presigned URLs). Either expose it on the host or route it through your reverse proxy.

### Firewall rules (host machine)

Open only the ports your users need. For a typical internal deployment:

```bash
# Ubuntu / Debian (ufw)
sudo ufw allow 80/tcp    # HTTP (redirect to HTTPS)
sudo ufw allow 443/tcp   # HTTPS (if you add TLS at the host level)
sudo ufw enable

# Rocky / AlmaLinux (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### DNS

Point your domain's A record at this machine's IP address:

```
bifrost.example.com.  IN  A  <your-server-ip>
```

For internal (RFC 1918) deployments, add the record to your internal DNS server or `hosts` file on client machines.

### Adding TLS (HTTPS) with a reverse proxy

#### Option A — Caddy (simplest, automatic Let's Encrypt)

Install Caddy on the host and create `/etc/caddy/Caddyfile`:

```
bifrost.example.com {
    reverse_proxy localhost:80
}
```

```bash
sudo systemctl enable --now caddy
```

Caddy automatically obtains and renews a free TLS certificate via Let's Encrypt.

#### Option B — Nginx + Certbot

```nginx
# /etc/nginx/sites-available/bifrost
server {
    listen 80;
    server_name bifrost.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name bifrost.example.com;

    ssl_certificate     /etc/letsencrypt/live/bifrost.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bifrost.example.com/privkey.pem;

    # Modern TLS settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers off;

    # Large file uploads
    client_max_body_size 100m;

    location / {
        proxy_pass         http://localhost:80;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
```

```bash
sudo certbot --nginx -d bifrost.example.com
sudo systemctl reload nginx
```

#### Option C — Internal deployment without public DNS (self-signed or internal CA)

If your machine is not internet-reachable, generate a self-signed certificate or use your organization's internal CA:

```bash
# Quick self-signed certificate (not for browsers without adding the CA)
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout /etc/ssl/private/bifrost.key \
  -out /etc/ssl/certs/bifrost.crt \
  -subj "/CN=bifrost.internal"
```

> Update `.env` to reflect HTTPS in `BIFROST_PUBLIC_URL` and `BIFROST_WEBAUTHN_ORIGIN` even for internal certificates so WebAuthn passkey registration works correctly.

### MinIO public access (required for direct file uploads/downloads)

If users will upload or download large files, their browsers need access to MinIO presigned URLs. Configure `BIFROST_S3_PUBLIC_ENDPOINT_URL` in `.env`:

```dotenv
# Route MinIO through your reverse proxy, or expose port 9000 directly
# This is the browser-facing URL for presigned uploads/downloads
BIFROST_S3_PUBLIC_ENDPOINT_URL=/s3
```

Then add a proxy rule for `/s3` → `http://localhost:9000` in your reverse proxy config.

---

## 6. Security Hardening

These steps take your deployment from "works" to "appropriately secured."

### 6.1 — Secrets management

The `setup.sh` script generates cryptographically random secrets. Never reuse the defaults from `.env.example`.

```bash
# Verify your secrets are not the development defaults
grep -E "POSTGRES_PASSWORD|RABBITMQ_PASSWORD|MINIO_ROOT_PASSWORD|BIFROST_SECRET_KEY" .env
```

- `BIFROST_SECRET_KEY` must be at least 32 characters (it signs all JWT tokens).
- Never commit `.env` to source control — it is already in `.gitignore`.

### 6.2 — Database access control

PostgreSQL is not exposed to the host by default. It only accepts connections from the internal Docker network through PgBouncer. Leave it that way — do not add `ports:` to the `postgres` service in `docker-compose.yml`.

If you need direct DB access for administration:

```bash
# Use exec into the container instead of opening a port
docker compose exec postgres psql -U bifrost -d bifrost
```

### 6.3 — Enable MFA

Bifrost ships with TOTP-based two-factor authentication. Enable it for all accounts:

```dotenv
# In .env
BIFROST_MFA_ENABLED=true
```

After restarting, users will be prompted to configure a TOTP app (Authy, Google Authenticator, etc.) on their next login.

### 6.4 — Enable WebAuthn (passkeys)

For phishing-resistant login, ensure WebAuthn is properly configured for your domain:

```dotenv
BIFROST_WEBAUTHN_RP_ID=bifrost.example.com
BIFROST_WEBAUTHN_RP_NAME=Bifrost
BIFROST_WEBAUTHN_ORIGIN=https://bifrost.example.com
```

WebAuthn **requires HTTPS** (except for `localhost`). This is another reason to set up TLS before inviting users.

### 6.5 — JWT token expiry

The defaults (30-minute access tokens, 7-day refresh tokens) are reasonable starting points. Tighten them for sensitive environments:

```dotenv
BIFROST_ACCESS_TOKEN_EXPIRE_MINUTES=15
BIFROST_REFRESH_TOKEN_EXPIRE_DAYS=1
```

### 6.6 — Redis security

Redis is exposed only on the internal Docker network and is not password-protected by default (the Docker network provides isolation). For additional defense-in-depth, add a Redis password:

1. Edit `docker-compose.yml` to add `--requirepass <password>` to the Redis command.
2. Add the Redis URL with credentials to `.env`:
   ```dotenv
   BIFROST_REDIS_URL=redis://:your-redis-password@redis:6379/0
   ```

### 6.7 — Keep Docker and images up to date

```bash
# Pull latest images and restart (run periodically)
docker compose pull
docker compose up -d

# Keep Docker Engine updated via your OS package manager
sudo apt-get update && sudo apt-get upgrade -y docker-ce
```

### 6.8 — Host OS hardening checklist

- [ ] Disable password-based SSH login; use SSH keys only  
  (`PasswordAuthentication no` in `/etc/ssh/sshd_config`)
- [ ] Firewall allows only ports 80, 443, and 22 from the internet
- [ ] Enable automatic security updates:
  ```bash
  # Ubuntu
  sudo apt-get install -y unattended-upgrades
  sudo dpkg-reconfigure --priority=low unattended-upgrades
  ```
- [ ] Regularly audit which users have `docker` group membership (docker group = root equivalent)
- [ ] Store secrets in a secrets manager (HashiCorp Vault, AWS Secrets Manager) rather than plain `.env` files for multi-person teams

### 6.9 — Data encryption at rest

Docker volumes store data on the host filesystem unencrypted by default. For sensitive MSP data, enable full-disk encryption on the host OS (LUKS on Linux, BitLocker on Windows Server) before deploying.

---

## 7. Day-2 Operations

### 7.1 — Backups

**PostgreSQL**

```bash
#!/bin/bash
# Suggested path: /etc/cron.daily/bifrost-backup

BACKUP_DIR=/var/backups/bifrost
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR

docker compose exec -T postgres \
  pg_dump -U bifrost bifrost | gzip > $BACKUP_DIR/postgres-$DATE.sql.gz

# Keep 30 days of backups
find $BACKUP_DIR -name "postgres-*.sql.gz" -mtime +30 -delete

echo "Backup saved: $BACKUP_DIR/postgres-$DATE.sql.gz"
```

Make it executable and schedule it:

```bash
chmod +x /etc/cron.daily/bifrost-backup
```

**MinIO (workspace files)**

```bash
# Install MinIO client (mc)
curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
chmod +x /usr/local/bin/mc

# Configure (run once)
mc alias set bifrost-local http://localhost:9000 <MINIO_ROOT_USER> <MINIO_ROOT_PASSWORD>

# Mirror all buckets to backup storage
mc mirror bifrost-local/bifrost /var/backups/bifrost/minio/
```

**Restore PostgreSQL**

```bash
zcat /var/backups/bifrost/postgres-YYYYMMDD-HHMMSS.sql.gz \
  | docker compose exec -T postgres psql -U bifrost -d bifrost
```

### 7.2 — Scaling workers

Workers are stateless — scale them horizontally to handle more concurrent jobs:

```bash
# Run 3 worker replicas
docker compose up -d --scale worker=3
```

Each additional worker increases the number of workflows that can execute in parallel. Workers share the RabbitMQ queue; the scheduler must always remain at 1 replica.

Monitor queue depth from the RabbitMQ management UI (only expose this port for admin access):

```bash
# Temporarily expose RabbitMQ management UI for inspection
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d rabbitmq
# Then visit http://localhost:15672 (default credentials in your .env)
```

### 7.3 — Updating Bifrost

```bash
# Pull latest code
git pull

# Pull latest Docker images (if using pre-built images)
docker compose pull

# Restart — the init container runs migrations automatically
docker compose up -d

# Watch migration output
docker compose logs -f init
```

> **Note:** Always read the release notes before upgrading. Database migrations are one-way; backup your database before any upgrade.

### 7.4 — Monitoring

**Health checks**

```bash
# Check all container health status
docker compose ps

# API health endpoint
curl http://localhost/api/health
```

**Logs**

```bash
docker compose logs -f api        # API errors and requests
docker compose logs -f worker     # Job execution
docker compose logs -f scheduler  # Scheduled tasks
docker compose logs -f postgres   # Database errors
```

**Resource usage**

```bash
docker stats   # Live CPU/memory usage per container
```

---

## 8. Promoting to Azure Production

When you are ready to move beyond self-hosted hardware to a fully managed Azure environment, the mapping is straightforward. Bifrost's architecture is already designed for this path.

### 8.1 — Azure service mapping

| Bifrost component | Azure service | Notes |
|-------------------|--------------|-------|
| PostgreSQL + pgvector | [Azure Database for PostgreSQL – Flexible Server](https://learn.microsoft.com/azure/postgresql/) | Enable the `vector` extension in the Azure portal |
| PgBouncer | Built-in connection pooling on Flexible Server | Azure Flexible Server includes built-in PgBouncer; verify your pooling mode (transaction vs session) matches the self-hosted PgBouncer config before migrating |
| RabbitMQ | [Azure Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/) (Advanced tier) or self-hosted RabbitMQ on AKS | Service Bus supports AMQP 1.0; aio-pika is compatible. Alternatively keep RabbitMQ as a pod. |
| Redis | [Azure Cache for Redis](https://learn.microsoft.com/azure/azure-cache-for-redis/) | Use the Standard or Premium tier for persistence |
| MinIO | [Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/) S3-compatible API (simplest), or MinIO on AKS backed by Azure Blob Storage | For the simplest path, point `BIFROST_S3_ENDPOINT_URL` at Azure Blob's S3-compatible endpoint. To keep MinIO on AKS with Azure Blob as its storage backend, configure MinIO's erasure coding settings. |
| API, Client, Scheduler, Worker | [Azure Kubernetes Service (AKS)](https://learn.microsoft.com/azure/aks/) | The `k8s/` directory already contains Kubernetes manifests |
| TLS / Ingress | [Azure Application Gateway](https://learn.microsoft.com/azure/application-gateway/) or nginx-ingress with cert-manager | Azure manages certificate renewal |
| Secrets | [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/) + [Secrets Store CSI Driver](https://learn.microsoft.com/azure/aks/csi-secrets-store-driver) | Replaces the `.env` file |
| Container images | [Azure Container Registry (ACR)](https://learn.microsoft.com/azure/container-registry/) | Push images built with `build.sh` here |

### 8.2 — Building and pushing images to ACR

```bash
# Authenticate to ACR
az acr login --name <your-acr-name>

# Build and push multi-platform images
./build.sh \
  --tag v1.0.0 \
  --registry <your-acr-name>.azurecr.io \
  --push
```

### 8.3 — AKS quick-start

```bash
# 1. Create a resource group and AKS cluster
az group create --name bifrost-rg --location eastus
az aks create \
  --resource-group bifrost-rg \
  --name bifrost-aks \
  --node-count 3 \
  --node-vm-size Standard_D4s_v5 \
  --enable-addons monitoring \
  --generate-ssh-keys

# 2. Get credentials
az aks get-credentials --resource-group bifrost-rg --name bifrost-aks

# 3. Deploy using the existing Kubernetes manifests
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic bifrost-secrets \
  --namespace=bifrost \
  --from-env-file=.env
kubectl apply -k k8s/

# 4. Verify
kubectl get pods -n bifrost
```

See `k8s/README.md` for full Kubernetes configuration details.

### 8.4 — Recommended Azure sizing

| AKS node pool | VM size | Replicas | Purpose |
|---------------|---------|----------|---------|
| System | Standard_D2s_v5 | 2 | Kubernetes system components |
| API | Standard_D4s_v5 | 2–3 | API and Scheduler pods |
| Worker | Standard_D4s_v5 | 3–10 (autoscale) | Workflow execution workers |

Recommended managed service tiers:

| Service | Recommended tier |
|---------|-----------------|
| Azure DB for PostgreSQL | General Purpose, 4 vCores, 16 GB RAM |
| Azure Cache for Redis | Standard C2 (6 GB) |
| Azure Blob Storage | LRS (hot tier) |
| Azure Service Bus (if used) | Standard |

### 8.5 — Cost estimates (rough guidance)

> Azure costs vary by region and commitment. These are approximate monthly figures for US East using pay-as-you-go pricing as of early 2025.

| Resource | Estimated monthly cost |
|----------|----------------------|
| AKS cluster (5 × Standard_D4s_v5) | ~$550–700 |
| Azure DB for PostgreSQL (4 vCores, 16 GB) | ~$150–200 |
| Azure Cache for Redis (Standard C2) | ~$90 |
| Azure Blob Storage (100 GB + transactions) | ~$5–15 |
| Azure Container Registry (Basic) | ~$5 |
| Load Balancer / Application Gateway | ~$30–80 |
| **Total estimate** | **~$830–1,100/month** |

Using your Azure Credits from the Microsoft partnership will eliminate these costs during your evaluation and initial production period.

### 8.6 — Production checklist for Azure

- [ ] All secrets stored in Azure Key Vault, not in `.env`
- [ ] ACR configured with geo-replication if multi-region
- [ ] AKS cluster has autoscaling enabled on the worker node pool
- [ ] PostgreSQL has automated backups enabled (Azure-managed, daily, 35-day retention)
- [ ] Redis persistence enabled (AOF or RDB snapshots)
- [ ] Azure Monitor and Container Insights enabled on AKS
- [ ] Network Policy enabled on AKS (restrict pod-to-pod traffic)
- [ ] Private endpoints configured for PostgreSQL, Redis, and Blob Storage (no public internet access)
- [ ] Azure Application Gateway WAF (Web Application Firewall) rules enabled
- [ ] The `scheduler` deployment remains at `replicas: 1` — it must not run as multiple instances

---

## 9. Sample Workflows (Bootstrapping)

Bifrost stores workflows as Python files in your organization's workspace. The repository includes ready-to-use example workflows under `api/tests/e2e/fixtures/workspace/`. Copy any of these into your workspace to have something running immediately.

### How workflows work

A workflow is a Python file containing one or more functions decorated with `@workflow`. Bifrost discovers, compiles, and makes them runnable from the web UI (manually, via schedule, or via webhook event) without any additional configuration:

```python
from bifrost import workflow, context

@workflow(
    name="my_workflow",
    description="A short description shown in the UI",
    category="My Category",           # groups workflows in the sidebar
    tags=["tag1", "tag2"],            # optional — used for search/filtering
    # schedule="0 9 * * *",          # optional — run on a cron schedule
)
async def my_workflow(param1: str, count: int = 1) -> dict:
    """Parameters become the form fields in the UI."""
    return {"result": f"Hello {param1}", "count": count}
```

### Example 1 — Simple greeting (manual run)

A minimal workflow that accepts form inputs and returns a result. Good first test to confirm execution is working.

```python
# File: greeting.py
import logging
from bifrost import workflow, context

logger = logging.getLogger(__name__)

@workflow(
    name="simple_greeting",
    description="Creates a personalized greeting",
    category="Examples",
    tags=["example", "greeting"]
)
async def simple_greeting(
    name: str,
    greeting_type: str = "Hello",
    include_timestamp: bool = False
) -> dict:
    import datetime

    greeting = f"{greeting_type}, {name}!"
    if include_timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        greeting += f" (at {timestamp})"

    logger.info(f"Generated greeting: {greeting}")
    return {
        "greeting": greeting,
        "name": name,
        "org_id": context.org_id   # context gives you org/user info at runtime
    }
```

### Example 2 — Scheduled workflow (cron)

Runs automatically on a schedule without any user action. Useful for nightly reports, recurring sync jobs, etc.

```python
# File: nightly_report.py
import logging
from bifrost import workflow

logger = logging.getLogger(__name__)

@workflow(
    name="nightly_report",
    description="Runs every night at 9 PM to summarize the day",
    category="Scheduled",
    tags=["scheduled", "report"],
    schedule="0 21 * * *",   # cron: every day at 9:00 PM
)
async def nightly_report() -> dict:
    # Put your actual logic here — call an API, query a DB, send an email, etc.
    logger.info("Nightly report executed")
    return {"status": "success", "message": "Report complete"}
```

### Example 3 — Multi-step workflow with loop

Demonstrates iteration and structured return values:

```python
# File: bulk_processor.py
import logging
from bifrost import workflow

logger = logging.getLogger(__name__)

@workflow(
    name="bulk_processor",
    description="Processes a list of items and returns results",
    category="Examples",
    tags=["example", "loop"]
)
async def bulk_processor(items_csv: str, dry_run: bool = True) -> dict:
    """
    items_csv: comma-separated list of items to process
    dry_run: if True, only simulate processing
    """
    items = [item.strip() for item in items_csv.split(",") if item.strip()]
    results = []

    for item in items:
        logger.info(f"Processing: {item} (dry_run={dry_run})")
        results.append({"item": item, "status": "simulated" if dry_run else "processed"})

    return {"processed": len(results), "dry_run": dry_run, "results": results}
```

### Uploading a workflow

1. In the Bifrost web UI, navigate to your organization's **Workspace**
2. Create a new Python file (or upload one)
3. Paste in any of the examples above
4. Bifrost hot-reloads the workspace — your workflow appears in the **Workflows** list within seconds
5. Click **Run** to execute it manually, or set a schedule in the `@workflow` decorator

### Where to find more examples

The E2E test fixtures contain several additional patterns you can adapt:

| File | Patterns demonstrated |
|------|-----------------------|
| `api/tests/e2e/fixtures/workspace/e2e_basic_workflow.py` | Basic form inputs, context access |
| `api/tests/e2e/fixtures/workspace/e2e_scheduled_workflow.py` | Cron scheduling |
| `api/tests/e2e/fixtures/workspace/e2e_test_workflow.py` | Loops, multiple return values |
| `api/tests/e2e/fixtures/workspace/e2e_cancellation_workflow.py` | Long-running / cancellable jobs |
| `api/tests/e2e/fixtures/workspace/e2e_form_workflows.py` | Form-integrated workflows (data loading, validation, conditional fields) |

---

## 10. Troubleshooting

### Containers not starting

```bash
# See which containers failed and why
docker compose ps
docker compose logs <service-name>
```

### Database connection errors

```bash
# Check PostgreSQL is healthy
docker compose exec postgres pg_isready -U bifrost

# Check PgBouncer can connect
docker compose logs pgbouncer

# Run migrations manually if the init container exited too early
docker compose run --rm init alembic upgrade head
```

### API returns 500 errors

```bash
docker compose logs api | tail -50
```

Look for `ERROR` or `CRITICAL` lines. Most startup errors are misconfigured environment variables.

### Workers not picking up jobs

```bash
docker compose logs worker | tail -30
```

If workers cannot connect to RabbitMQ, check that `RABBITMQ_PASSWORD` in `.env` matches the value used to create the RabbitMQ user.

### Passkeys / WebAuthn not working

WebAuthn requires that `BIFROST_WEBAUTHN_ORIGIN` exactly matches the URL in the browser address bar (including `https://`). After changing the domain, restart the API container:

```bash
docker compose restart api
```

### Resetting to a clean state

```bash
# WARNING: This deletes all data
docker compose down -v
docker compose up -d
```

---

## Quick-Reference Cheat Sheet

```bash
# Start Bifrost
docker compose up -d

# Stop Bifrost
docker compose down

# View all logs
docker compose logs -f

# View a single service's logs
docker compose logs -f api

# Run a database migration
docker compose run --rm init alembic upgrade head

# Scale workers
docker compose up -d --scale worker=3

# Backup database
docker compose exec -T postgres pg_dump -U bifrost bifrost | gzip > backup.sql.gz

# Restore database
zcat backup.sql.gz | docker compose exec -T postgres psql -U bifrost bifrost

# Pull latest and restart
git pull && docker compose pull && docker compose up -d

# Open a psql shell
docker compose exec postgres psql -U bifrost -d bifrost

# Check container health
docker compose ps
```
