# Protocol v1 (plugin -> server -> client)

## 1) UDP payload from plugin (3DS -> server)

JSON object:

```json
{
  "schemaVersion": 1,
  "event": "plugin_start",
  "titleId": "00040000001B5000"
}
```

Fields:
- `schemaVersion` (number): protocol version, currently `1` (matches `PROTOCOL_SCHEMA_VERSION` in `plugin_main.c`).
- `event` (string): `plugin_start` or `heartbeat`.
- `titleId` (string): 16-char uppercase hex title ID.

> Game exit is detected server-side via the watchdog: if no heartbeat is received
> within `DRPC_WATCHDOG_TIMEOUT_SEC` seconds, the server broadcasts a `clear` event.

## 2) WebSocket payload from server (server -> PC client)

JSON object:

```json
{
  "type": "presence",
  "schemaVersion": 1,
  "event": "heartbeat",
  "titleId": "00040000001B5000",
  "name": "Mario Kart 7",
  "icon": "https://..."
}
```

Fields:
- `type` (string): `presence`.
- `schemaVersion` (number): forwarded protocol version.
- `event` (string): original plugin event.
- `titleId` (string): normalized 16-char uppercase hex.
- `name` (string): resolved game name (fallback: `Title <titleId>`).
- `icon` (string): resolved icon URL, or empty string.

## Compatibility

- Client keeps a legacy fallback for older server payloads containing only `name` and `icon`.
- Server accepts messages without `schemaVersion` and forwards the value as-is (default `0`).

