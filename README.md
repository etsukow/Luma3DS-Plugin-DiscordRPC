# Luma3DS Plugin — Discord RPC

Show your current 3DS game as a Discord Rich Presence status — automatically, in real time.

![Discord RPC preview](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?logo=discord&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/github/license/etsukow/Luma3DS-Plugin-DiscordRPC)

---

## How it works

```
3DS (Luma3DS plugin) ──UDP──▶ server ──WebSocket──▶ client ──▶ Discord RPC
```

1. The `.3gx` plugin runs in the background on your 3DS and sends UDP packets containing the current title ID.
2. The server resolves the game name and icon via [api.nlib.cc](https://api.nlib.cc) and broadcasts it over WebSocket.
3. The PC client receives the game info and updates your Discord status.

Protocol details: [`docs/protocol-v1.md`](docs/protocol-v1.md).

---

## Requirements

**To use:**
- A 3DS with **custom firmware (Luma3DS)**
- **Discord desktop app** running on your PC (web app not supported)
- PC running **Windows, macOS, or Linux**

**To build / run from source:**
- **Docker** — to compile the `.3gx` plugin
- **Python 3.11+** — to run the server and client from source

---

## Quick start

### 1. Install the plugin on your 3DS

Download the latest `default.3gx` from the [Releases](https://github.com/etsukow/Luma3DS-Plugin-DiscordRPC/releases/latest) page and copy it to your SD card:

```
SD:/luma/plugins/default.3gx
```

Enable the plugin loader in Luma3DS settings (hold **SELECT** on boot) and make sure **"Game patching"** is on.

Enable the plugin loader in Rosalina menu (hold **L+DOWN+SELECT** once console booted) and make sure **Plugin Loader** is enabled.

> The plugin runs automatically in the background whenever you launch a game.

---

### 2. Install and start the client

Download the executable for your platform from the [Releases](https://github.com/etsukow/Luma3DS-Plugin-DiscordRPC/releases/latest) page:

| Platform | File |
|---|---|
| Windows | `3DS-DiscordRPC-windows.exe` |
| macOS | `3DS-DiscordRPC-macos` |
| Linux | `3DS-DiscordRPC-linux` |

Place the executable anywhere on your machine and run it once:

**Windows** — double-click `3DS-DiscordRPC-windows.exe`.

**macOS** — right-click → Open (required to bypass Gatekeeper on first launch):
```zsh
chmod +x 3DS-DiscordRPC-macos
./3DS-DiscordRPC-macos
```

**Linux**:
```bash
chmod +x 3DS-DiscordRPC-linux
./3DS-DiscordRPC-linux
```

On **first launch**, the client registers itself as a login item and starts running in the background automatically — no terminal stays open. From then on it starts with your PC at every login.

The server URL and Discord application ID are compiled into the executable — no configuration needed.

Launch a game on your 3DS — your Discord status will update automatically.

---

## Running from source *(optional)*

> For developers or advanced users who want to run the server and client directly with Python.

### 1. Configure

```zsh
cp .env.example .env
```

Edit `.env` — the only required values are:

```dotenv
# Your PC's local IP (the 3DS must be able to reach it)
DRPC_SERVER_WS_URL=wss://192.168.1.XX:8765

# Your Discord application ID — create one at developer.discord.com
DRPC_DISCORD_APP_ID=your_app_id_here
```

> `DRPC_SERVER_WS_URL` is used both to configure the client and to embed the server IP in the `.3gx` binary at build time.

---

### 2. Start the server

```zsh
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
python server/main.py
```

The server listens on:
- **UDP `0.0.0.0:5005`** — receives packets from the 3DS plugin
- **WebSocket `0.0.0.0:8765`** — broadcasts game info to clients

---

### 3. Start the client

```zsh
source .venv/bin/activate
pip install -r client/requirements.txt
python client/main.py
```


---

## Building the plugin yourself *(optional)*

> Only needed if you want to compile the `.3gx` with your own server IP embedded,
> or if no pre-built binary is available for your version.

Build the `.3gx` binary using Docker (no toolchain setup required):

```zsh
# Make sure DRPC_SERVER_WS_URL is set in .env with your PC's local IP
docker compose run --rm builder
```

The compiled `default.3gx` will appear in the project root. Copy it to your SD card as described above.

---

## Configuration reference

All values can be set in `.env` or as environment variables (when running from source).

> **For the pre-built executables**, `DRPC_SERVER_WS_URL` and `DRPC_DISCORD_APP_ID` are
> compiled in at build time via GitHub secrets — no configuration file needed.

### Runtime variables (from source only)

| Variable | Default                | Description |
|---|------------------------|---|
| `DRPC_SERVER_WS_URL` | `wss://127.0.0.1:8765` | WebSocket URL of the server |
| `UDP_PORT` | `5005`                 | UDP port the plugin sends to |
| `DRPC_UDP_HOST` | `0.0.0.0`              | Server UDP bind address |
| `DRPC_UDP_PORT` | `5005`                 | Server UDP bind port |
| `DRPC_WS_HOST` | `0.0.0.0`              | Server WebSocket bind address |
| `DRPC_WS_PORT` | `8765`                 | Server WebSocket bind port |
| `DRPC_FALLBACK_ICON` | `nintendo_3ds`         | Icon key used when none is found for a title |
| `DRPC_RPC_MIN_INTERVAL` | `15`                   | Minimum seconds between RPC updates (heartbeats) |
| `DRPC_WATCHDOG_TIMEOUT_SEC` | `25`                   | Seconds without a heartbeat before RPC is cleared |
| `DRPC_API_TIMEOUT_SEC` | `5.0`                  | Timeout for title info API requests |

---

## TitleID mapping

Some titles (updates, DLCs, regional variants) have a different TitleID than their base game and may not be found by the API. You can remap them in `server/tid_map.json`:

```json
{
  "0004000000185A00": "0004000000164600"
}
```

The server will resolve and display the canonical title instead.

---

## Troubleshooting

**Discord status not showing up**
- Make sure the Discord **desktop app** is running (not the web version)
- Go to Discord **Settings → Activity Privacy** and enable "Display current activity as a status message"
- Check that `DRPC_SERVER_WS_URL` in `.env` matches your PC's local IP

**No events received on the server**
- Verify `DRPC_SERVER_WS_URL` in `.env` contains the right IP and rebuild the `.3gx`
- Check that UDP port `5005` is not blocked by your firewall
- Make sure the 3DS and your PC are on the same network

**Plugin not loading**
- Confirm the file is at `SD:/luma/plugins/default.3gx`
- Make sure "Game patching" is enabled in Luma3DS settings (hold SELECT on boot)

---

## License

MIT — see [LICENSE](LICENSE)