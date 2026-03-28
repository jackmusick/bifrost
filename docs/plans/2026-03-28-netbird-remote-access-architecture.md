# NetBird Remote Access Architecture

## Goal

Provide reliable remote browser and CLI access to the Bifrost dev environment
without depending on the lab LAN, VPN-to-LAN hacks, or the MetalLB ingress VIP
as the only access path.

## Current Working Access Paths

Browser/UI:
- `https://bifrost-mtg.eu1.netbird.services`

CLI/API:
- `https://bifrost-api-mtg.eu1.netbird.services`

The CLI path is now usable for:
- `bifrost cli api`
- `bifrost sync`
- `bifrost watch`

Validated on 2026-03-28:
- API requests return integration data
- `bifrost sync .` returns `Already up to date.`
- `scripts/bifrost-watch-dev.sh .` completes initial sync and keeps the
  WebSocket connected

## Why The Private VIP Path Is Not The Primary Remote Path

We tested the NetBird-routed private ingress path with:
- `10.1.23.240.nip.io`
- `bifrost.nb.midtowntg.com`
- direct `10.1.23.114:443`

Findings:
- NetBird DNS resolution works
- NetBird route selection works
- remote packets reach `bifrost-poc` on `wt0`
- local HTTPS on `bifrost-poc` works
- but the subnet-routed HTTPS path to the ingress VIP / node `:443` does not
  reliably return traffic to remote NetBird peers

This makes the private-subnet ingress path unsuitable as the primary remote
workflow path today.

## Current NetBird Topology

We are using NetBird `Networks`, not the older standalone route model.

Live topology:
- one `kubernetes` network
- a router attached to the `kubernetes` peer group
- routing peers include:
  - the operator-managed router pods
  - `bifrost-proxy`
  - `bifrost-poc-host`

Important resource names currently in NetBird:
- `kubernetes.default.svc.cluster.local`
- `client.bifrost.svc.cluster.local`
- `api.bifrost.svc.cluster.local`
- `bifrost.nb.midtowntg.com`
- `10.1.23.240.nip.io`

## Stateful Host Changes On `bifrost-poc`

The current working CLI/API path depends on stateful changes on the Debian VM
hosting the cluster:

- package installed:
  - `nginx`
- nginx site added:
  - `/etc/nginx/sites-available/bifrost-api-proxy`
- nginx site enabled:
  - `/etc/nginx/sites-enabled/bifrost-api-proxy`
- nginx listens on:
  - `0.0.0.0:18080`
- backend proxied by nginx:
  - `http://10.43.69.125:8000`

This host proxy is the stable backend for the NetBird API reverse-proxy service.

Temporary historical state:
- a Python host proxy and a `bifrost-api-proxy.service` systemd unit were used
  during debugging
- that service is now disabled and should be removed in a later cleanup pass

## Current Tradeoffs

Good:
- remote browser access works
- remote CLI access works
- `bifrost watch` works remotely again
- access no longer depends on the lab LAN being directly reachable

Bad:
- browser and CLI use separate public NetBird reverse-proxy hostnames
- the setup still depends on NetBird cloud reverse proxy, which is best effort
- the Debian host proxy is currently snowflake state
- policies still need tightening from broad defaults to a dedicated admin group

## Recommended Simplification Path

Target architecture:
- `bifrost-poc-host` remains the stable NetBird routing peer
- one host-level reverse proxy on `bifrost-poc` handles both UI and API
- one private hostname is used for browser and CLI
- TLS is terminated on the host-level proxy with a private CA-backed cert
- NetBird DNS resolves that private hostname directly to the stable host peer
- NetBird cloud reverse proxy becomes optional rather than required

This would reduce:
- dependency on NetBird cloud proxy infrastructure
- reliance on the MetalLB VIP for remote work
- split-brain browser/CLI hostname behavior

## Cleanup / Hardening Backlog

1. Tighten NetBird access policies from `All` to `bifrost-admins`.
2. Remove the temporary in-cluster `bifrost-proxy` path if it is no longer
   needed.
3. Remove the disabled temporary Python proxy service from `bifrost-poc`.
4. Codify the host nginx proxy as managed config instead of snowflake state.
5. Decide whether to migrate away from NetBird cloud reverse proxy entirely once
   the stable host-backed private hostname is ready.
