#!/usr/bin/env python3
"""Reference bridge server for Luma3DS-Plugin-DiscordRPC.

Flow:
3DS plugin (UDP v1) -> this server -> PC clients (WebSocket)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from typing import Dict, Optional, Set

from websockets.asyncio.server import ServerConnection, serve

UDP_HOST = os.getenv("DRPC_UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("DRPC_UDP_PORT", "5005"))
WS_HOST = os.getenv("DRPC_WS_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("DRPC_WS_PORT", "8765"))
API_TEMPLATE = os.getenv("DRPC_TITLE_API_TEMPLATE", "https://api.nlib.cc/ctr/{tid}")
API_TIMEOUT_SEC = float(os.getenv("DRPC_API_TIMEOUT_SEC", "5.0"))

# Watchdog: clear RPC after this many seconds without a heartbeat.
# The plugin sends a heartbeat every 10 s; we give it 2× margin.
WATCHDOG_TIMEOUT_SEC = float(os.getenv("DRPC_WATCHDOG_TIMEOUT_SEC", "25.0"))

# TitleID mapping: maps IDs missing from the API (updates, DLCs, regional
# variants) to their canonical base game ID.
_TID_MAP_PATH = os.path.join(os.path.dirname(__file__), "tid_map.json")


def _load_tid_map(path: str) -> Dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            raw: dict = json.load(f)
        return {
            k.upper(): v.upper()
            for k, v in raw.items()
            if isinstance(k, str) and isinstance(v, str) and not k.startswith("_")
        }
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


TID_MAP: Dict[str, str] = _load_tid_map(_TID_MAP_PATH)


class BridgeState:
    def __init__(self) -> None:
        self.clients: Set[ServerConnection] = set()
        self.cache: Dict[str, Dict[str, str]] = {}
        self.error_cache: Dict[str, str] = {}
        self.last_title_id: Optional[str] = None
        self.last_seen: Optional[float] = None  # monotonic timestamp of last UDP packet


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


def normalize_tid(raw_tid: str) -> Optional[str]:
    tid = raw_tid.strip().upper()
    if tid.startswith("0X"):
        tid = tid[2:]
    if len(tid) != 16:
        return None
    try:
        int(tid, 16)
    except ValueError:
        return None
    return tid


def fetch_title_info(tid: str) -> Dict[str, str]:
    req = urllib.request.Request(
        API_TEMPLATE.format(tid=tid),
        headers={"User-Agent": "luma-drpc-server/1.0"},
    )
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SEC) as resp:
        payload = resp.read()

    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected API payload")

    name = data.get("name")
    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    icon = media.get("icon") if isinstance(media, dict) else None

    return {
        "name": name if isinstance(name, str) and name else f"Title {tid}",
        "icon": icon if isinstance(icon, str) else "",
    }


async def resolve_title(state: BridgeState, tid: str) -> Dict[str, str]:
    if tid in state.cache:
        return state.cache[tid]
    if tid in state.error_cache:
        return {"name": f"Title {tid}", "icon": ""}

    try:
        resolved = await asyncio.to_thread(fetch_title_info, tid)
        state.cache[tid] = resolved
        return resolved
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        state.error_cache[tid] = str(exc)
        print(f"[{now_iso()}] titleId={tid} api_error={exc}", flush=True)
        return {"name": f"Title {tid}", "icon": ""}


async def broadcast_json(state: BridgeState, payload: Dict[str, object]) -> None:
    if not state.clients:
        return

    wire = json.dumps(payload, separators=(",", ":"))
    dead_clients: Set[ServerConnection] = set()

    for client in state.clients:
        try:
            await client.send(wire)
        except Exception:
            dead_clients.add(client)

    if dead_clients:
        state.clients.difference_update(dead_clients)


class UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, state: BridgeState):
        self.state = state

    def datagram_received(self, data: bytes, addr) -> None:
        host, port = addr[0], addr[1]
        try:
            text = data.decode("utf-8").strip()
            msg = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"[{now_iso()}] {host}:{port} invalid_payload", flush=True)
            return

        if not isinstance(msg, dict):
            return

        asyncio.create_task(self._handle_message(msg, host, port))

    async def _handle_message(self, msg: Dict[str, object], host: str, port: int) -> None:
        event = msg.get("event")
        title_id_raw = msg.get("titleId")
        schema_version = msg.get("schemaVersion", 0)

        if not isinstance(event, str) or not isinstance(title_id_raw, str):
            return

        tid = normalize_tid(title_id_raw)
        if tid is None:
            return

        # Always refresh the watchdog timestamp, even for silent heartbeats.
        self.state.last_seen = asyncio.get_running_loop().time()

        # Remap to canonical base-game TitleID if needed.
        canonical_tid = TID_MAP.get(tid, tid)
        if canonical_tid != tid:
            print(f"[{now_iso()}] tid_remap {tid} -> {canonical_tid}", flush=True)

        if canonical_tid == self.state.last_title_id and event == "heartbeat":
            return
        self.state.last_title_id = canonical_tid

        resolved = await resolve_title(self.state, canonical_tid)

        payload = {
            "type": "presence",
            "schemaVersion": schema_version,
            "event": event,
            "titleId": canonical_tid,
            "name": resolved.get("name", f"Title {canonical_tid}"),
            "icon": resolved.get("icon", ""),
        }

        print(
            f"[{now_iso()}] udp={host}:{port} event={event} titleId={canonical_tid} "
            f"name={payload['name']}",
            flush=True,
        )

        await broadcast_json(self.state, payload)


async def watchdog(state: BridgeState) -> None:
    """Broadcast a 'clear' event when no UDP packet has been received for WATCHDOG_TIMEOUT_SEC."""
    while True:
        await asyncio.sleep(5)
        if state.last_seen is None:
            continue
        elapsed = asyncio.get_running_loop().time() - state.last_seen
        if elapsed >= WATCHDOG_TIMEOUT_SEC:
            print(f"[{now_iso()}] watchdog: no heartbeat for {elapsed:.0f}s — clearing RPC", flush=True)
            state.last_seen = None
            state.last_title_id = None
            await broadcast_json(state, {"type": "clear"})


async def ws_handler(conn: ServerConnection, state: BridgeState) -> None:
    state.clients.add(conn)
    print(f"[{now_iso()}] ws_client_connected total={len(state.clients)}", flush=True)

    # Catch up the newly connected client with the current state.
    if state.last_title_id and state.last_seen is not None:
        resolved = await resolve_title(state, state.last_title_id)
        catchup = {
            "type": "presence",
            "event": "plugin_start",
            "titleId": state.last_title_id,
            "name": resolved.get("name", f"Title {state.last_title_id}"),
            "icon": resolved.get("icon", ""),
        }
        try:
            await conn.send(json.dumps(catchup, separators=(",", ":")))
        except Exception:
            pass

    try:
        await conn.wait_closed()
    finally:
        state.clients.discard(conn)
        print(f"[{now_iso()}] ws_client_disconnected total={len(state.clients)}", flush=True)


async def main() -> None:
    state = BridgeState()

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UdpProtocol(state),
        local_addr=(UDP_HOST, UDP_PORT),
    )

    print(f"[{now_iso()}] UDP listening on {UDP_HOST}:{UDP_PORT}", flush=True)
    print(f"[{now_iso()}] WebSocket listening on {WS_HOST}:{WS_PORT}", flush=True)
    print(f"[{now_iso()}] Watchdog timeout: {WATCHDOG_TIMEOUT_SEC:.0f}s", flush=True)

    async with serve(lambda conn: ws_handler(conn, state), WS_HOST, WS_PORT):
        asyncio.create_task(watchdog(state))
        await asyncio.Future()

    transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{now_iso()}] Server stopped", flush=True)
