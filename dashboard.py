"""
Dashboard web server — serves live trading state over HTTP.
Access from any browser on the local network: http://<pi-ip>:8080
"""
import json
import os
from pathlib import Path
from aiohttp import web

CONFIG = json.load(open("config.json"))
PORT = CONFIG.get("dashboard_port", 8080)
STATE_FILE = CONFIG.get("state_file", "state.json")
TRADES_FILE = CONFIG.get("trades_log", "trades.json")
STATIC_DIR = Path(__file__).parent / "static"


def _read_json(path: str) -> dict | list:
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return {}


async def handle_index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_state(request: web.Request) -> web.Response:
    state = _read_json(STATE_FILE)
    trades = _read_json(TRADES_FILE)
    if not isinstance(trades, list):
        trades = []
    payload = {**state, "trades": trades[-50:]}
    return web.json_response(payload)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_state)
    app.router.add_static("/static", STATIC_DIR)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT, print=lambda s: print(f"[dashboard] {s}"))
