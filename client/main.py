#!/usr/bin/env python3
"""3DS Discord RPC — Client PC

Lance simplement cet exe, c'est tout.
Se connecte au serveur et met à jour ton Discord RPC automatiquement.

Run:
    pip install pypresence websocket-client
    python main.py
"""

from __future__ import annotations

import datetime as dt
import json
import signal
import ssl
import sys
import time
from typing import Optional

import websocket
try:
    import certifi
except ImportError:
    certifi = None
from pypresence import Presence, exceptions as rpc_exc

from config import ClientConfig, load_config
from service import install as install_service, start as start_service, acquire_instance_lock



# ── Helpers ───────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


# ── Discord RPC ───────────────────────────────────────────────────────────────
class RPCClient:
    def __init__(self, app_id: str, fallback_icon: str, min_interval_sec: int):
        self._app_id = app_id
        self._fallback_icon = fallback_icon
        self._min_interval_sec = min_interval_sec
        self._rpc: Optional[Presence] = None
        self._connected = False
        self._last_update = 0.0

    def _disconnect(self) -> None:
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._connected = False

    def _connect(self) -> bool:
        try:
            self._rpc = Presence(self._app_id)
            self._rpc.connect()
            self._connected = True
            print(f"[{now_iso()}] Discord RPC connecté ✓", flush=True)
            return True
        except Exception as exc:
            print(f"[{now_iso()}] Discord RPC connexion échouée : {exc}", flush=True)
            self._disconnect()
            return False

    def _update_once(self, name: str, icon: str, start_time: int) -> None:
        self._rpc.update(
            details=name,
            state="Nintendo 3DS",
            large_image=icon if icon else self._fallback_icon,
            large_text=name,
            start=start_time,
        )

    def update(self, name: str, icon: str, start_time: int, force: bool = False) -> None:
        if not force and time.monotonic() - self._last_update < self._min_interval_sec:
            return
        if not self._connected:
            if not self._connect():
                return
        try:
            self._update_once(name, icon, start_time)
            self._last_update = time.monotonic()
            print(f"[{now_iso()}] RPC -> {name}", flush=True)
        except rpc_exc.InvalidID:
            print(f"[{now_iso()}] RPC : Application ID invalide.", flush=True)
        except Exception as exc:
            print(f"[{now_iso()}] RPC update échoué : {exc}", flush=True)
            self._disconnect()
            if not self._connect():
                return
            try:
                self._update_once(name, icon, start_time)
                self._last_update = time.monotonic()
                print(f"[{now_iso()}] RPC -> {name} (après reconnexion)", flush=True)
            except Exception as retry_exc:
                print(f"[{now_iso()}] RPC retry échoué : {retry_exc}", flush=True)
                self._disconnect()

    def clear(self) -> None:
        if self._connected and self._rpc:
            try:
                self._rpc.clear()
                print(f"[{now_iso()}] RPC effacé (menu HOME)", flush=True)
            except Exception:
                self._disconnect()
        self._last_update = 0.0

    def close(self) -> None:
        self._disconnect()


# ── WebSocket ─────────────────────────────────────────────────────────────────
def run(config: ClientConfig) -> None:
    rpc = RPCClient(config.discord_app_id, config.fallback_icon, config.rpc_min_interval)
    game_start = 0
    last_name = ""
    sslopt = None

    if config.server_ws_url.startswith("wss://"):
        sslopt = {"cert_reqs": ssl.CERT_REQUIRED}
        if certifi is not None:
            sslopt["ca_certs"] = certifi.where()

    def on_open(ws):
        print(f"[{now_iso()}] Connecté au serveur {config.server_ws_url} ✓", flush=True)

    def on_message(ws, message):
        nonlocal game_start, last_name
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "clear":
            rpc.clear()
            last_name = ""
            game_start = 0
            return

        if msg.get("type") == "presence":
            name = msg.get("name", "")
            icon = msg.get("icon", "")
            event = msg.get("event", "")
        else:
            # Legacy fallback format.
            name = msg.get("name", "")
            icon = msg.get("icon", "")
            event = ""

        if not isinstance(name, str) or not isinstance(icon, str):
            return

        if not name:
            return

        is_start = (event == "plugin_start")

        if name != last_name or is_start:
            game_start = int(time.time())
            last_name = name

        rpc.update(name, icon, game_start, force=is_start)

    def on_close(ws, code, reason):
        print(f"[{now_iso()}] Déconnecté ({code}), reconnexion dans 5s...", flush=True)
        rpc.clear()

    def on_error(ws, error):
        print(f"[{now_iso()}] Erreur : {error}", flush=True)

    while True:
        ws = websocket.WebSocketApp(
            config.server_ws_url,
            on_open=on_open,
            on_message=on_message,
            on_close=on_close,
            on_error=on_error,
        )
        ws.run_forever(reconnect=5, sslopt=sslopt)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    if not acquire_instance_lock():
        # Another instance is already running — exit silently.
        return 0

    config = load_config()

    def stop(_s, _f):
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)


    if install_service():
        print(f"[{now_iso()}] Service installé — démarrage en arrière-plan.", flush=True)
        start_service()
        return 0

    print(f"[{now_iso()}] 3DS Discord RPC démarré", flush=True)
    print(f"[{now_iso()}] Serveur WS: {config.server_ws_url}", flush=True)

    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
