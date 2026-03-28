# NetBird Remote Access Architecture

## Goal

Provide reliable remote browser and CLI access to the Bifrost dev environment
without depending on the lab LAN, VPN-to-LAN hacks, or the MetalLB ingress VIP
as the only access path.

## Current Working Access Paths

Canonical direct-mesh path:
- browser/UI: `https://bifrost-poc-host.netbird.cloud:18443`
- CLI/API: `https://bifrost-poc-host.netbird.cloud:18443`

The direct CLI path is usable for:
- `bifrost cli api`
- `bifrost sync`
- `bifrost watch`

Validated on 2026-03-28:
- `GET /health` succeeds on the direct hostname
- `bifrost sync .` returns `Already up to date.`
- `scripts/bifrost-watch-dev.sh .` completes initial sync and keeps the
  WebSocket connected when pointed at the direct hostname

Historical fallback paths:
- `https://bifrost-mtg.eu1.netbird.services`
- `https://bifrost-api-mtg.eu1.netbird.services`

These should no longer be treated as the primary workflow path.

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

Current stable host peer:
- DNS: `bifrost-poc-host.netbird.cloud`
- peer is now persistent, not ephemeral

Important resource names currently in NetBird:
- `kubernetes.default.svc.cluster.local`
- `client.bifrost.svc.cluster.local`
- `api.bifrost.svc.cluster.local`
- `bifrost.nb.midtowntg.com`
- `10.1.23.240.nip.io`

## Stateful Host Changes On `bifrost-poc`

The current direct path still depends on stateful host configuration on the
Debian VM hosting the cluster.

Installed / configured:
- package installed:
  - `nginx`
- nginx site files:
  - `/etc/nginx/sites-available/bifrost-api-proxy`
  - `/etc/nginx/sites-available/bifrost-direct`
- enabled site symlinks:
  - `/etc/nginx/sites-enabled/bifrost-api-proxy`
  - `/etc/nginx/sites-enabled/bifrost-direct`
- current direct entrypoint:
  - `:18443` on `bifrost-poc-host.netbird.cloud`
- current API helper path:
  - `:18080`

Current host-backed behavior:
- `:18443` serves both the Bifrost UI shell and API/auth/ws paths
- `:18080` still serves the API-only helper path

Temporary historical state:
- a Python host proxy and a `bifrost-api-proxy.service` systemd unit were used
  during debugging
- that service is now disabled and should be removed

## Current Tradeoffs

Good:
- remote browser access works over direct mesh
- remote CLI access works over direct mesh
- `bifrost watch` works remotely again
- the stable host peer is persistent now
- access no longer depends on NetBird hosted reverse proxy

Bad:
- the working direct path currently depends on host nginx state
- `:443` on the stable host still does not behave reliably over NetBird
- policies still need tightening from broad defaults to a dedicated admin group
- the old hosted reverse-proxy paths are still present and should be deprecated

## Recommended Simplification Path

Target architecture:
- `bifrost-poc-host` remains the stable NetBird routing peer
- one canonical hostname is used for browser and CLI
- that hostname should use normal `:443`
- k3s ingress should own the canonical `:443` path directly on the host
- host nginx should no longer be required for normal access
- NetBird DNS should resolve the canonical hostname directly to the stable host
  peer

This would reduce:
- dependency on host snowflake proxy state
- reliance on the MetalLB VIP for remote work
- split-brain browser/CLI hostname behavior

## Cleanup / Hardening Backlog

1. Tighten NetBird access policies from `All` to `bifrost-admins`.
2. Remove the temporary in-cluster `bifrost-proxy` path if it is no longer
   needed.
3. Remove the disabled temporary Python proxy service from `bifrost-poc`.
4. Investigate and fix why direct host `:443` still hangs over NetBird while
   direct host `:18443` works.
5. Once `:443` is reliable, remove the host nginx workaround and deprecated
   hosted reverse-proxy assumptions.
