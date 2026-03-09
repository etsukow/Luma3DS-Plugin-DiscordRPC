#!/usr/bin/env python3
"""Bridge server for Luma3DS-Plugin-DiscordRPC — multi-user edition.

Flow:
  3DS plugin (UDP)  ──► server ──► desktop app (WebSocket, auth by token)

Endpoints:
  POST /token           — provision a unique token for a new client
  GET  /plugin/build    — build & return a personalised .3gx for ?token=<tok>

UDP payload  (plugin ──► server):
  {"schemaVersion":1,"event":"plugin_start","titleId":"…","token":"…"}

WebSocket auth frame (client ──► server, first message):
  {"type":"auth","token":"…"}
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Set

from websockets.asyncio.server import ServerConnection, serve as ws_serve

# ── Environment ───────────────────────────────────────────────────────────────
UDP_HOST             = os.getenv("DRPC_UDP_HOST", "0.0.0.0")
UDP_PORT             = int(os.getenv("DRPC_UDP_PORT", "5005"))
WS_HOST              = os.getenv("DRPC_WS_HOST", "0.0.0.0")
WS_PORT              = int(os.getenv("DRPC_WS_PORT", "8765"))
HTTP_HOST            = os.getenv("DRPC_HTTP_HOST", "0.0.0.0")
HTTP_PORT            = int(os.getenv("DRPC_HTTP_PORT", "8766"))
API_TEMPLATE         = os.getenv("DRPC_TITLE_API_TEMPLATE", "https://api.nlib.cc/ctr/{tid}")
API_TIMEOUT_SEC      = float(os.getenv("DRPC_API_TIMEOUT_SEC", "5.0"))
WATCHDOG_TIMEOUT_SEC = float(os.getenv("DRPC_WATCHDOG_TIMEOUT_SEC", "25.0"))
# Public UDP hostname reported to new clients so the 3DS knows where to send.
PUBLIC_UDP_HOST      = os.getenv("DRPC_PUBLIC_UDP_HOST", "127.0.0.1")
DOCKER_COMPOSE_FILE  = os.getenv(
    "DRPC_DOCKER_COMPOSE_FILE",
    str(Path(__file__).parent / "docker-compose.yml"),
)
_TID_MAP_PATH = os.path.join(os.path.dirname(__file__), "tid_map.json")


# ── Helpers ───────────────────────────────────────────────────────────────────
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


def fetch_title_info(tid: str) -> Dict[str, str]:
    req = urllib.request.Request(
        API_TEMPLATE.format(tid=tid),
        headers={"User-Agent": "luma-drpc-server/2.0"},
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


# ── Per-token state ───────────────────────────────────────────────────────────

class TokenState:
    """All mutable state for one user / one token."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.clients: Set[ServerConnection] = set()
        self.cache: Dict[str, Dict[str, str]] = {}
        self.error_cache: Dict[str, str] = {}
        self.last_title_id: Optional[str] = None
        self.last_seen: Optional[float] = None

    async def resolve_title(self, tid: str) -> Dict[str, str]:
        if tid in self.cache:
            return self.cache[tid]
        if tid in self.error_cache:
            return {"name": f"Title {tid}", "icon": ""}
        try:
            resolved = await asyncio.to_thread(fetch_title_info, tid)
            self.cache[tid] = resolved
            return resolved
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            self.error_cache[tid] = str(exc)
            print(f"[{now_iso()}] titleId={tid} api_error={exc}", flush=True)
            return {"name": f"Title {tid}", "icon": ""}

    async def broadcast(self, payload: Dict) -> None:
        if not self.clients:
            return
        wire = json.dumps(payload, separators=(",", ":"))
        dead: Set[ServerConnection] = set()
        for client in self.clients:
            try:
                await client.send(wire)
            except Exception:
                dead.add(client)
        self.clients.difference_update(dead)


# ── Global registry ───────────────────────────────────────────────────────────

class Registry:
    """Maps token strings → TokenState."""

    def __init__(self) -> None:
        self._states: Dict[str, TokenState] = {}

    def provision(self) -> str:
        """Create and register a fresh cryptographically-random token."""
        tok = secrets.token_urlsafe(24)
        self._states[tok] = TokenState(tok)
        print(f"[{now_iso()}] token_provisioned token={tok[:8]}…", flush=True)
        return tok

    def get(self, token: str) -> Optional[TokenState]:
        return self._states.get(token)

    def get_or_create(self, token: str) -> TokenState:
        if token not in self._states:
            self._states[token] = TokenState(token)
        return self._states[token]

    def all_states(self):
        return list(self._states.values())


# ── UDP Protocol ──────────────────────────────────────────────────────────────

class UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def datagram_received(self, data: bytes, addr) -> None:
        host, port = addr[0], addr[1]
        try:
            msg = json.loads(data.decode("utf-8").strip())
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"[{now_iso()}] {host}:{port} invalid_payload", flush=True)
            return
        if not isinstance(msg, dict):
            return
        asyncio.create_task(self._handle(msg, host, port))

    async def _handle(self, msg: Dict, host: str, port: int) -> None:
        event        = msg.get("event")
        title_id_raw = msg.get("titleId")
        schema_ver   = msg.get("schemaVersion", 0)
        tok          = msg.get("token", "")

        if not isinstance(event, str) or not isinstance(title_id_raw, str):
            return
        tid = normalize_tid(title_id_raw)
        if tid is None:
            return

        # Prefer explicit token; fall back to source IP for legacy plugin builds.
        if tok and isinstance(tok, str):
            state = self.registry.get_or_create(tok)
        else:
            state = self.registry.get_or_create(f"__ip_{host}")

        state.last_seen = asyncio.get_running_loop().time()

        canonical_tid = TID_MAP.get(tid, tid)
        if canonical_tid != tid:
            print(f"[{now_iso()}] tid_remap {tid} -> {canonical_tid}", flush=True)

        if canonical_tid == state.last_title_id and event == "heartbeat":
            return
        state.last_title_id = canonical_tid

        resolved = await state.resolve_title(canonical_tid)
        payload = {
            "type": "presence",
            "schemaVersion": schema_ver,
            "event": event,
            "titleId": canonical_tid,
            "name": resolved.get("name", f"Title {canonical_tid}"),
            "icon": resolved.get("icon", ""),
        }
        label = (tok[:8] + "…") if tok else f"legacy-ip:{host}"
        print(
            f"[{now_iso()}] udp={host}:{port} token={label} "
            f"event={event} titleId={canonical_tid} name={payload['name']}",
            flush=True,
        )
        await state.broadcast(payload)


# ── WebSocket handler ─────────────────────────────────────────────────────────

AUTH_TIMEOUT_SEC = 15.0


async def ws_handler(conn: ServerConnection, registry: Registry) -> None:
    """Each WS client must send {"type":"auth","token":"…"} as its first frame."""
    try:
        raw = await asyncio.wait_for(conn.recv(), timeout=AUTH_TIMEOUT_SEC)
        msg = json.loads(raw)
    except Exception:
        await conn.close(1008, "auth timeout or invalid frame")
        return

    if not isinstance(msg, dict) or msg.get("type") != "auth":
        await conn.close(1008, "expected auth frame")
        return

    tok = msg.get("token", "")
    if not isinstance(tok, str) or not tok:
        await conn.close(1008, "missing token")
        return

    state = registry.get_or_create(tok)
    state.clients.add(conn)
    print(f"[{now_iso()}] ws_auth token={tok[:8]}… clients={len(state.clients)}", flush=True)

    # Catch up: send current presence if 3DS is already playing.
    if state.last_title_id and state.last_seen is not None:
        resolved = await state.resolve_title(state.last_title_id)
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
        print(f"[{now_iso()}] ws_disconnect token={tok[:8]}… clients={len(state.clients)}", flush=True)


# ── Watchdog ──────────────────────────────────────────────────────────────────

async def watchdog(registry: Registry) -> None:
    """Per-token watchdog: clears RPC when no heartbeat arrives within the timeout."""
    while True:
        await asyncio.sleep(5)
        loop_time = asyncio.get_running_loop().time()
        for state in registry.all_states():
            if state.last_seen is None:
                continue
            if loop_time - state.last_seen >= WATCHDOG_TIMEOUT_SEC:
                print(
                    f"[{now_iso()}] watchdog: token={state.token[:8]}… "
                    f"no heartbeat — clearing RPC",
                    flush=True,
                )
                state.last_seen = None
                state.last_title_id = None
                await state.broadcast({"type": "clear"})


# ── HTTP API (minimal asyncio stream server) ──────────────────────────────────

async def http_handler(registry: Registry,
                       reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> None:
    try:
        req_line = (await asyncio.wait_for(reader.readline(), timeout=5.0)).decode(errors="replace").strip()
        if not req_line:
            return
        parts = req_line.split(" ")
        if len(parts) < 2:
            return
        method, path_qs = parts[0], parts[1]

        # Consume HTTP headers.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line in (b"\r\n", b"\n", b""):
                break

        if method == "POST" and path_qs.rstrip("/") == "/token":
            tok = registry.provision()
            _respond(writer, 201, "Created",
                     json.dumps({"token": tok,
                                 "udp_host": PUBLIC_UDP_HOST,
                                 "udp_port": UDP_PORT}).encode())

        elif method == "GET" and path_qs.startswith("/plugin/build"):
            qs = path_qs.split("?", 1)[1] if "?" in path_qs else ""
            params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            await _serve_plugin(params.get("token", ""), writer)

        else:
            _respond(writer, 404, "Not Found", b'{"error":"not found"}')

    except Exception as exc:
        print(f"[{now_iso()}] http_error: {exc}", flush=True)
    finally:
        writer.close()


def _respond(writer: asyncio.StreamWriter, status: int, reason: str, body: bytes,
             ct: str = "application/json", extra: Optional[Dict[str, str]] = None) -> None:
    h = (f"HTTP/1.1 {status} {reason}\r\n"
         f"Content-Type: {ct}\r\n"
         f"Content-Length: {len(body)}\r\n"
         f"Connection: close\r\n")
    if extra:
        h += "".join(f"{k}: {v}\r\n" for k, v in extra.items())
    writer.write((h + "\r\n").encode() + body)


async def _serve_plugin(token: str, writer: asyncio.StreamWriter) -> None:
    if not token:
        _respond(writer, 400, "Bad Request", b'{"error":"missing token"}')
        return

    print(f"[{now_iso()}] plugin build request token={token[:8]}…", flush=True)

    build_dir = Path(__file__).parent

    compose_file = Path(DOCKER_COMPOSE_FILE)
    if not compose_file.exists():
        _respond(writer, 503, "Service Unavailable",
                 b'{"error":"build environment not configured (missing docker compose file)"}')
        return
    if shutil.which("docker") is None:
        _respond(writer, 503, "Service Unavailable",
                 b'{"error":"build environment not configured (docker missing)"}')
        return

    env = {
        **os.environ,
        "DRPC_TOKEN": token,
        "DRPC_SERVER_WS_URL": f"ws://{PUBLIC_UDP_HOST}:{UDP_PORT}",
        "PATH": os.environ.get("PATH", ""),
    }
    cmd = ["docker", "compose", "-f", str(compose_file), "run", "--rm", "builder"]
    cwd = str(compose_file.parent)

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True, cwd=cwd, env=env, timeout=120,
        )
    except subprocess.TimeoutExpired:
        _respond(writer, 504, "Gateway Timeout", b'{"error":"build timed out"}')
        return
    except FileNotFoundError:
        _respond(writer, 503, "Service Unavailable", b'{"error":"docker not found"}')
        return

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")[-512:]
        print(f"[{now_iso()}] plugin build failed: {err}", flush=True)
        _respond(writer, 500, "Internal Server Error",
                 json.dumps({"error": "build failed", "detail": err}).encode())
        return

    built = build_dir / "default.3gx"
    if not built.exists():
        _respond(writer, 500, "Internal Server Error",
                 b'{"error":"artefact not found after build"}')
        return

    data = built.read_bytes()
    _respond(writer, 200, "OK", data, ct="application/octet-stream",
             extra={"X-Plugin-Version": "0.1.1",
                    "Content-Disposition": 'attachment; filename="discord-rpc.3gx"'})
    print(f"[{now_iso()}] plugin served {len(data)} bytes token={token[:8]}…", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    registry = Registry()
    loop = asyncio.get_running_loop()

    # UDP
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UdpProtocol(registry), local_addr=(UDP_HOST, UDP_PORT))
    print(f"[{now_iso()}] UDP  listening on {UDP_HOST}:{UDP_PORT}", flush=True)

    # WebSocket
    async with ws_serve(lambda conn: ws_handler(conn, registry), WS_HOST, WS_PORT):
        print(f"[{now_iso()}] WS   listening on {WS_HOST}:{WS_PORT}", flush=True)

        # HTTP API
        http_server = await asyncio.start_server(
            lambda r, w: http_handler(registry, r, w), HTTP_HOST, HTTP_PORT)
        print(f"[{now_iso()}] HTTP listening on {HTTP_HOST}:{HTTP_PORT}", flush=True)
        print(f"[{now_iso()}] Watchdog: {WATCHDOG_TIMEOUT_SEC:.0f}s", flush=True)

        asyncio.create_task(watchdog(registry))

        async with http_server:
            await asyncio.Future()

    transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{now_iso()}] Server stopped", flush=True)
