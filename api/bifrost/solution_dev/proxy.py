"""The single-origin local dev server for `bifrost solution start`.

Routes:
  POST /api/workflows/execute  → local FunctionHost when the path::fn ref is one
                                 of THIS workspace's functions; else upstream.
  /api/*                       → reverse-proxy to the dev API (data-plane).
  everything else              → reverse-proxy to the Vite dev server (the app).

The upstream proxy injects the CLI token (Authorization) and the resolved org
(X-Bifrost-Org) so data-plane calls run under the chosen --org, matching deployed.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from aiohttp import web

# Hop-by-hop headers we must not forward when reverse-proxying.
_STRIP = {"host", "content-length", "transfer-encoding", "connection", "keep-alive"}


@dataclass(frozen=True)
class DevProxyConfig:
    upstream_url: str   # the dev API, e.g. http://localhost:37791
    token: str          # CLI access token
    app_id: str         # chosen app's manifest UUID
    org_id: str | None  # resolved --org (or None → caller's default org)


def build_dev_app(cfg: DevProxyConfig, host, vite_url: str) -> web.Application:
    app = web.Application()
    app["cfg"] = cfg
    app["host"] = host
    app["vite_url"] = vite_url.rstrip("/")
    app["http"] = httpx.AsyncClient(timeout=120.0)

    app.router.add_post("/api/workflows/execute", _execute_handler)
    app.router.add_route("*", "/api/{tail:.*}", _api_proxy_handler)
    app.router.add_route("*", "/{tail:.*}", _vite_proxy_handler)

    async def _close(app):
        await app["http"].aclose()

    app.on_cleanup.append(_close)
    return app


def _auth_headers(cfg: DevProxyConfig, incoming) -> dict[str, str]:
    headers = {k: v for k, v in incoming.items() if k.lower() not in _STRIP}
    headers["Authorization"] = f"Bearer {cfg.token}"
    if cfg.org_id:
        headers["X-Bifrost-Org"] = cfg.org_id
    headers["X-Bifrost-App"] = cfg.app_id
    return headers


async def _execute_handler(request: web.Request) -> web.Response:
    cfg: DevProxyConfig = request.app["cfg"]
    host = request.app["host"]
    body = await request.json()
    ref = body.get("workflow_id", "")

    # Local path::fn that we discovered → run it in-process (own-first, locally).
    if "::" in str(ref) and host.has(ref):
        try:
            result = await host.run(ref, body.get("input_data") or {})
        except Exception as exc:
            return web.json_response({"detail": f"Local workflow error: {exc}"}, status=500)
        return web.json_response({"status": "completed", "result": result})

    # Otherwise proxy to the dev API (UUIDs, _repo/ refs, sibling installs).
    resp = await request.app["http"].post(
        f"{cfg.upstream_url}/api/workflows/execute",
        json=body,
        headers=_auth_headers(cfg, request.headers),
    )
    return web.Response(
        body=resp.content, status=resp.status_code,
        content_type=resp.headers.get("content-type", "application/json").split(";")[0],
    )


async def _api_proxy_handler(request: web.Request) -> web.Response:
    cfg: DevProxyConfig = request.app["cfg"]
    data = await request.read()
    resp = await request.app["http"].request(
        request.method,
        f"{cfg.upstream_url}{request.rel_url}",
        content=data or None,
        headers=_auth_headers(cfg, request.headers),
    )
    return web.Response(
        body=resp.content, status=resp.status_code,
        headers={"content-type": resp.headers.get("content-type", "application/json")},
    )


async def _vite_proxy_handler(request: web.Request) -> web.Response:
    vite_url = request.app["vite_url"]
    data = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP}
    resp = await request.app["http"].request(
        request.method,
        f"{vite_url}{request.rel_url}",
        content=data or None,
        headers=headers,
    )
    return web.Response(
        body=resp.content, status=resp.status_code,
        headers={"content-type": resp.headers.get("content-type", "text/html")},
    )
