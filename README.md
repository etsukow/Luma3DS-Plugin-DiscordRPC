# Luma3DS Plugin — Discord RPC

Show your current 3DS game as a Discord Rich Presence status — automatically, in real time.  
**Multi-user ready**: every player gets their own isolated Discord integration.

![Discord RPC preview](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?logo=discord&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/github/license/etsukow/Luma3DS-Plugin-DiscordRPC)

---

## How it works

```
3DS plugin (UDP) ──► bridge server ──► Desktop app (WebSocket) ──► Discord RPC
                           │
                     HTTP API (:8766)
                     POST /token
                     GET  /plugin/build
```

Each user has a **unique token** provisioned at first install:

1. Desktop app install flow calls `POST /token` → server returns a secret token.
2. The server builds a personalised `.3gx` plugin with that token baked in (`GET /plugin/build`).
3. The `.3gx` is downloaded and you copy it to your 3DS SD card.
4. The app keeps a background connection to the server with your token.
5. The 3DS plugin sends UDP packets containing your token + current title ID.
6. The server routes each packet **only** to the matching app session → your Discord only.

Protocol details: [`docs/protocol-v1.md`](docs/protocol-v1.md).

---

> **Compatibility note**
> The plugin may crash on some titles due to `UsePrivateMemory: true`.
> Known compatibility reports: [#2](https://github.com/etsukow/Luma3DS-Plugin-DiscordRPC/issues/2).

---

## Requirements

- A 3DS with **Luma3DS custom firmware**
- **Discord desktop app** running on your PC (web app not supported)
- PC running **Windows, macOS, or Linux**

---

## Quick start (recommended)

### 1. Download and install the desktop app

Download the latest Tauri build for your OS from the [Releases](https://github.com/etsukow/Luma3DS-Plugin-DiscordRPC/releases/latest) page.

On first launch, click **Install** in the app.

This will:
- Request your unique token from the server
- Download your personalised `discord-rpc.3gx` plugin (stored in your app config directory)
- Start the local daemon that keeps your Discord status up to date

### 2. Copy the plugin to your 3DS SD card

```
# Global fallback (all games)
SD:/luma/plugins/default/discord-rpc.3gx

# Or per-game (replace 00040000001B5000 with the title ID)
SD:/luma/plugins/00040000001B5000/discord-rpc.3gx
```

The plugin file path is shown in the app after install.

### 3. Enable the plugin on your 3DS

Hold **SELECT** while booting a game to open the Luma plugin menu and enable the plugin.

That's it — your Discord status will update automatically whenever you play.

---

## Running the server (self-hosted)

```sh
cd server
pip install -r requirements.txt

# Expose the public UDP address so clients know where to point their 3DS:
export DRPC_PUBLIC_UDP_HOST=1.2.3.4   # your server's public IP

python main.py
```

The server listens on three ports:
| Port | Protocol | Purpose |
|------|----------|---------|
| 5005 | UDP | Receives events from 3DS plugins |
| 8765 | WebSocket | Streams presence updates to desktop app |
| 8766 | HTTP | Token provisioning & plugin builds |

All ports are configurable via environment variables (see [`docs/protocol-v1.md`](docs/protocol-v1.md)).

---

## Building from source

### Desktop app (Tauri)

```sh
cd client-tauri
npm ci
npm run tauri build
```

### 3DS plugin (requires Docker)

The server builds personalised plugins on demand. To build manually:

```sh
# Token is injected at compile time
cd server
DRPC_TOKEN=your_token DRPC_SERVER_WS_URL=ws://1.2.3.4:5005 \
  docker compose run --rm builder
# Output: default.3gx
```

---

## License

[MIT](LICENSE)
