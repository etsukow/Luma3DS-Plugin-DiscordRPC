"""Auto-start service management for 3DS Discord RPC client.

Installs / uninstalls a startup entry so the client launches automatically
when the user logs in.

  Windows : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  (registry)
  macOS   : ~/Library/LaunchAgents/cc.luma3ds.discord-rpc.plist      (LaunchAgent)
  Linux   : ~/.config/systemd/user/luma3ds-discord-rpc.service       (systemd user unit)
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

APP_NAME = "luma3ds-discord-rpc"
DISPLAY_NAME = "3DS Discord RPC"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _exe_path() -> str:
    """Absolute path of the running executable (frozen or plain Python)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # Running as plain script — use the python interpreter + this package.
    return f"{sys.executable} {Path(__file__).parent / 'main.py'}"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


# ── Windows ───────────────────────────────────────────────────────────────────

def _win_is_installed() -> bool:
    return _win_registered_exe() is not None


def _win_registered_exe() -> str | None:
    import winreg  # type: ignore
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        value, _ = winreg.QueryValueEx(key, DISPLAY_NAME)
        winreg.CloseKey(key)
        return value
    except (OSError, FileNotFoundError):
        return None


def _win_install() -> None:
    import winreg  # type: ignore
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, DISPLAY_NAME, 0, winreg.REG_SZ, sys.executable)
    winreg.CloseKey(key)


def _win_uninstall() -> None:
    import winreg  # type: ignore
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, DISPLAY_NAME)
        winreg.CloseKey(key)
    except (OSError, FileNotFoundError):
        pass


# ── macOS ─────────────────────────────────────────────────────────────────────

_MACOS_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"cc.{APP_NAME}.plist"

_MACOS_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>cc.{app_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/stderr.log</string>
</dict>
</plist>
"""


def _macos_log_dir() -> Path:
    log_dir = Path.home() / "Library" / "Logs" / DISPLAY_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _macos_is_installed() -> bool:
    return _MACOS_PLIST_PATH.exists()


def _macos_registered_exe() -> str | None:
    if not _MACOS_PLIST_PATH.exists():
        return None
    try:
        import plistlib
        data = plistlib.loads(_MACOS_PLIST_PATH.read_bytes())
        args = data.get("ProgramArguments", [])
        return args[0] if args else None
    except Exception:
        return None


def _macos_install() -> None:
    _MACOS_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = _MACOS_PLIST_TEMPLATE.format(
        app_name=APP_NAME,
        exe=sys.executable,
        log_dir=_macos_log_dir(),
    )
    _MACOS_PLIST_PATH.write_text(plist, encoding="utf-8")
    subprocess.run(
        ["launchctl", "load", "-w", str(_MACOS_PLIST_PATH)],
        check=False,
    )


def _macos_uninstall() -> None:
    if _MACOS_PLIST_PATH.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(_MACOS_PLIST_PATH)],
            check=False,
        )
        _MACOS_PLIST_PATH.unlink(missing_ok=True)


# ── Linux (systemd user) ──────────────────────────────────────────────────────

_LINUX_SERVICE_PATH = (
    Path.home() / ".config" / "systemd" / "user" / f"{APP_NAME}.service"
)

_LINUX_SERVICE_TEMPLATE = """\
[Unit]
Description={display_name}
After=network.target graphical-session.target

[Service]
Type=simple
ExecStart={exe}
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
"""


def _linux_is_installed() -> bool:
    return _LINUX_SERVICE_PATH.exists()


def _linux_registered_exe() -> str | None:
    if not _LINUX_SERVICE_PATH.exists():
        return None
    for line in _LINUX_SERVICE_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            return line[len("ExecStart="):].strip()
    return None


def _linux_install() -> None:
    _LINUX_SERVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    unit = _LINUX_SERVICE_TEMPLATE.format(
        display_name=DISPLAY_NAME,
        exe=sys.executable,
    )
    _LINUX_SERVICE_PATH.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", APP_NAME], check=False)


def _linux_uninstall() -> None:
    if _LINUX_SERVICE_PATH.exists():
        subprocess.run(["systemctl", "--user", "disable", APP_NAME], check=False)
        _LINUX_SERVICE_PATH.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)


# ── Public API ────────────────────────────────────────────────────────────────

def _registered_exe() -> str | None:
    system = platform.system()
    if system == "Windows":
        return _win_registered_exe()
    if system == "Darwin":
        return _macos_registered_exe()
    if system == "Linux":
        return _linux_registered_exe()
    return None


def is_installed() -> bool:
    system = platform.system()
    if system == "Windows":
        return _win_is_installed()
    if system == "Darwin":
        return _macos_is_installed()
    if system == "Linux":
        return _linux_is_installed()
    return False


def install() -> None:
    """Register the client as a login item, or update the entry if the exe path changed."""
    if not _is_frozen():
        # Don't register startup when running as plain Python script.
        return

    registered = _registered_exe()
    current = sys.executable

    if registered == current:
        # Already up-to-date, nothing to do.
        return

    system = platform.system()
    if system not in ("Windows", "Darwin", "Linux"):
        return

    if registered is not None:
        # Path changed (new version installed elsewhere) — reinstall.
        uninstall()
        print(f"[service] Updating auto-start: {registered} -> {current}", flush=True)

    if system == "Windows":
        _win_install()
    elif system == "Darwin":
        _macos_install()
    elif system == "Linux":
        _linux_install()

    if registered is None:
        print(f"[service] Auto-start registered ({system})", flush=True)


def uninstall() -> None:
    """Remove the login item registration."""
    system = platform.system()
    if system == "Windows":
        _win_uninstall()
    elif system == "Darwin":
        _macos_uninstall()
    elif system == "Linux":
        _linux_uninstall()
    print(f"[service] Auto-start removed ({system})", flush=True)

