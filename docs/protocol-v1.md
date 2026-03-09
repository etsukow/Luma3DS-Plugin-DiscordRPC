# Protocol v2 — multi-user token routing

## Overview

```
3DS plugin (UDP) ──► bridge server ──► PC client (WebSocket)
                          │
                    HTTP API  (:8766)
                    POST /token
                    GET  /plugin/build
                    GET  /client/release
```

Each user has a **unique token** (32-char URL-safe base64) that is:

1. Provisioned once by `POST /token` (at client install time).
2. Compiled into the user's personal `.3gx` plugin by `GET /plugin/build?token=<tok>`.
3. Sent in every UDP packet by the plugin.
4. Used by the PC client to authenticate its WebSocket connection.

This ensures **complete isolation**: user A's 3DS activity never reaches user B's Discord.

---

## 1) HTTP API  (server — port 8766)

### `POST /token`
Provision a new token.

**Request:** empty body  
**Response 201:**
```json
{ "token": "abc123…", "udp_host": "1.2.3.4", "udp_port": 5005 }
```

### `GET /plugin/build?token=<tok>`
Trigger a Docker build of the `.3gx` plugin with `DRPC_TOKEN` and `DRPC_SERVER_WS_URL`
baked in. Streams the resulting binary.

**Response 200:** `application/octet-stream` — the `.3gx` file  
**Header:** `X-Plugin-Version: 0.1.x`

### `GET /client/release?os=<os>&arch=<arch>&current=<ver>`
Returns metadata for the latest PC client binary (for auto-update).

**Response 200:** JSON `{ "version", "url", "sha256", "filename" }`  
**Response 204:** already up to date / no manifest configured

---

## 2) UDP payload  (plugin → server, port 5005)

```json
{
  "schemaVersion": 1,
  "event": "plugin_start",
  "titleId": "00040000001B5000",
  "token": "abc123…"
}
```

Fields:
- `schemaVersion` — protocol version (`1`).
- `event` — `plugin_start` or `heartbeat`.
- `titleId` — 16-char uppercase hex title ID.
- `token` — user token injected at build time. **Absent on legacy builds** (server falls back to routing by source IP).

---

## 3) WebSocket  (server → PC client, port 8765)

### Authentication (client → server, first frame)

```json
{ "type": "auth", "token": "abc123…" }
```

The server closes the connection (code 1008) if no valid auth frame arrives within 15 s.

### Presence update (server → client)

```json
{
  "type": "presence",
  "schemaVersion": 1,
  "event": "heartbeat",
  "titleId": "00040000001B5000",
  "name": "Mario Kart 7",
  "icon": "https://…"
}
```

### Clear event (server → client)

```json
{ "type": "clear" }
```

Sent when the watchdog fires (no heartbeat for `WATCHDOG_TIMEOUT_SEC` seconds, default 25 s).

---

## 4) Environment variables

### Server
| Variable | Default | Description |
|---|---|---|
| `DRPC_UDP_HOST` | `0.0.0.0` | UDP bind address |
| `DRPC_UDP_PORT` | `5005` | UDP port |
| `DRPC_WS_HOST` | `0.0.0.0` | WebSocket bind address |
| `DRPC_WS_PORT` | `8765` | WebSocket port |
| `DRPC_HTTP_HOST` | `0.0.0.0` | HTTP API bind address |
| `DRPC_HTTP_PORT` | `8766` | HTTP API port |
| `DRPC_PUBLIC_UDP_HOST` | `127.0.0.1` | UDP host reported to clients via `/token` |
| `DRPC_DOCKER_COMPOSE_FILE` | `../docker-compose.yml` | Path to compose file for on-demand plugin builds |
| `DRPC_WATCHDOG_TIMEOUT_SEC` | `25` | Seconds without heartbeat before RPC clear |
| `DRPC_CLIENT_RELEASE_FILE` | _(empty)_ | Path to client release manifest JSON |

### PC client (`drpc` Go binary)
| Variable | Default | Description |
|---|---|---|
| `DRPC_SERVER_WS` | `wss://api.etsukow.com` | WebSocket URL |
| `DRPC_SERVER_API` | `https://api.etsukow.com` | HTTP API URL |

---

## 5) First-run flow

```
drpc install
  │
  ├─ POST /token  ──────────────────────► server provisions token
  │                ◄── { token, udp_host, udp_port }
  │
  ├─ GET /plugin/build?token=<tok>  ────► server builds .3gx with token baked in
  │                ◄── discord-rpc.3gx
  │
  └─ installs OS service (Windows Service / launchd / systemd)
       └─ drpc run  ──► WS connect  ──► {"type":"auth","token":"…"}
```

The `.3gx` must be copied to the 3DS SD card:
- `SD:/luma/plugins/<TitleID>/discord-rpc.3gx`  (per-game)
- `SD:/luma/plugins/default/discord-rpc.3gx`    (global fallback)
