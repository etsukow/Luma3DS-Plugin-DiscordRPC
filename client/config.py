from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

# ── Build-time constants ──────────────────────────────────────────────────────
# `build_constants.py` is committed with local defaults and overwritten in CI
# before PyInstaller runs, so frozen builds embed the release endpoint.
from build_constants import BUILT_IN_SERVER_WS_URL

# DRPC_DISCORD_APP_ID is public and hardcoded.
_DISCORD_APP_ID = "1480019559606911057"


@dataclass(frozen=True)
class ClientConfig:
    server_ws_url: str
    discord_app_id: str
    fallback_icon: str
    rpc_min_interval: int


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _pick(name: str, env_file_values: Dict[str, str], default: str) -> str:
    from_env = os.getenv(name)
    if from_env is not None and from_env.strip() != "":
        return from_env.strip()
    from_file = env_file_values.get(name)
    if from_file is not None and from_file.strip() != "":
        return from_file.strip()
    return default


def load_config() -> ClientConfig:
    _default_env = Path(os.getenv("DRPC_CLIENT_ENV_FILE", ".env"))
    # Also check next to this script (useful when running from a different cwd).
    _script_env = Path(__file__).parent / ".env"
    _root_env = Path(__file__).parent.parent / ".env"
    env_file_path = next(
        (p for p in (_default_env, _script_env, _root_env) if p.exists()),
        _default_env,
    )
    env_file_values = _parse_env_file(env_file_path)

    rpc_min_interval_raw = _pick("DRPC_RPC_MIN_INTERVAL", env_file_values, "15")
    try:
        rpc_min_interval = int(rpc_min_interval_raw)
    except ValueError:
        rpc_min_interval = 15
    if rpc_min_interval < 1:
        rpc_min_interval = 1

    return ClientConfig(
        server_ws_url=_pick("DRPC_SERVER_WS_URL", env_file_values, BUILT_IN_SERVER_WS_URL),
        discord_app_id=_DISCORD_APP_ID,
        fallback_icon=_pick("DRPC_FALLBACK_ICON", env_file_values, "nintendo_3ds"),
        rpc_min_interval=rpc_min_interval,
    )
