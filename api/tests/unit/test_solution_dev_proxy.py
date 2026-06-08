import socket

import httpx
from aiohttp import web

from bifrost.solution_dev.proxy import DevProxyConfig, build_dev_app


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StubHost:
    def __init__(self, refs):
        self._refs = set(refs)
        self.last_call = None

    def has(self, ref):
        return ref in self._refs

    async def run(self, ref, params):
        self.last_call = (ref, params)
        return {"ran_local": ref, "params": params}


def _make_upstream(record):
    async def execute(request):
        record["execute_body"] = await request.json()
        return web.json_response({"ran_upstream": True})

    async def other(request):
        record["other_path"] = request.path
        record["other_org"] = request.headers.get("X-Bifrost-Org")
        return web.json_response({"upstream_other": True})

    app = web.Application()
    app.router.add_post("/api/workflows/execute", execute)
    app.router.add_route("*", "/api/{tail:.*}", other)
    return app


async def _serve(app, port):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner


async def test_local_path_ref_runs_in_function_host():
    record = {}
    up_port, dev_port = _free_port(), _free_port()
    up_runner = await _serve(_make_upstream(record), up_port)
    host = _StubHost({"functions/hello.py::main"})
    cfg = DevProxyConfig(upstream_url=f"http://127.0.0.1:{up_port}", token="t", app_id="A", org_id="O")
    dev_runner = await _serve(build_dev_app(cfg, host, vite_url="http://127.0.0.1:1"), dev_port)
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"http://127.0.0.1:{dev_port}/api/workflows/execute",
                             json={"workflow_id": "functions/hello.py::main", "input_data": {"x": 1}, "app_id": "A"})
        assert r.status_code == 200
        assert r.json()["result"] == {"ran_local": "functions/hello.py::main", "params": {"x": 1}}
        assert host.last_call == ("functions/hello.py::main", {"x": 1})
        assert "execute_body" not in record  # never hit upstream
    finally:
        await dev_runner.cleanup()
        await up_runner.cleanup()


async def test_unknown_ref_proxies_to_upstream():
    record = {}
    up_port, dev_port = _free_port(), _free_port()
    up_runner = await _serve(_make_upstream(record), up_port)
    host = _StubHost(set())
    cfg = DevProxyConfig(upstream_url=f"http://127.0.0.1:{up_port}", token="t", app_id="A", org_id="O")
    dev_runner = await _serve(build_dev_app(cfg, host, vite_url="http://127.0.0.1:1"), dev_port)
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"http://127.0.0.1:{dev_port}/api/workflows/execute",
                             json={"workflow_id": "11111111-1111-1111-1111-111111111111", "input_data": {}, "app_id": "A"})
        assert r.status_code == 200
        assert r.json()["ran_upstream"] is True
        assert record["execute_body"]["app_id"] == "A"
    finally:
        await dev_runner.cleanup()
        await up_runner.cleanup()


async def test_other_api_path_proxies_with_org_header():
    record = {}
    up_port, dev_port = _free_port(), _free_port()
    up_runner = await _serve(_make_upstream(record), up_port)
    host = _StubHost(set())
    cfg = DevProxyConfig(upstream_url=f"http://127.0.0.1:{up_port}", token="t", app_id="A", org_id="O")
    dev_runner = await _serve(build_dev_app(cfg, host, vite_url="http://127.0.0.1:1"), dev_port)
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"http://127.0.0.1:{dev_port}/api/tables/foo")
        assert r.status_code == 200
        assert r.json()["upstream_other"] is True
        assert record["other_path"] == "/api/tables/foo"
        assert record["other_org"] == "O"
    finally:
        await dev_runner.cleanup()
        await up_runner.cleanup()
