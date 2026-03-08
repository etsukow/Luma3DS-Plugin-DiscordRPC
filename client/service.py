"""Auto-start service management for 3DS Discord RPC client.

Installs / uninstalls a startup entry so the client launches automatically
when the user logs in.

  Windows : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  (registry)
  macOS   : ~/Library/LaunchAgents/cc.luma3ds.discord-rpc.plist      (LaunchAgent)
  Linux   : ~/.config/systemd/user/luma3ds-discord-rpc.service       (systemd user unit)
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
import tempfile

APP_NAME = "luma3ds-discord-rpc"
DISPLAY_NAME = "3DS Discord RPC"

# ── Single-instance lock ──────────────────────────────────────────────────────

_LOCK_FILE = Path(tempfile.gettempdir()) / f"{APP_NAME}.lock"
_lock_fh = None  # kept alive to hold the lock


def acquire_instance_lock() -> bool:
    """Try to acquire a process-level lock. Returns False if another instance is running."""
    global _lock_fh
    if platform.system() == "Windows":
        import msvcrt  # type: ignore
        try:
            _lock_fh = open(_LOCK_FILE, "w")
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            _lock_fh.write(str(os.getpid()))
            _lock_fh.flush()
            return True
        except OSError:
            return False
    else:
        import fcntl  # type: ignore
        try:
            _lock_fh = open(_LOCK_FILE, "w")
            fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fh.write(str(os.getpid()))
            _lock_fh.flush()
            return True
        except OSError:
            return False

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


def install() -> bool:
    """Register the client as a login item, or update the entry if the exe path changed.

    Returns True if the service was installed or updated, False if already up-to-date.
    """
    if not _is_frozen():
        return False

    registered = _registered_exe()
    current = sys.executable

    if registered == current:
        # Already up-to-date, nothing to do.
        return False

    system = platform.system()
    if system not in ("Windows", "Darwin", "Linux"):
        return False

    if registered is not None:
        # Path changed (new version installed elsewhere) — reinstall.
        uninstall()
        print(f"[service] Updating auto-start: {registered} -> {current}", flush=True)
    else:
        print(f"[service] Auto-start registered ({system})", flush=True)

    if system == "Windows":
        _win_install()
    elif system == "Darwin":
        _macos_install()
    elif system == "Linux":
        _linux_install()

    return True


def start() -> None:
    """Start the service detached from the current terminal session.
    No-op if an instance is already running (lock held).
    """
    # Check if already running before spawning.
    try:
        import fcntl  # type: ignore
        fh = open(_LOCK_FILE, "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.close()
        # Lock acquired → nobody running, safe to start.
    except (ImportError, OSError):
        # ImportError = Windows (handled below), OSError = already running.
        if platform.system() != "Windows":
            return  # already running on Unix

    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(
            ["launchctl", "start", f"cc.{APP_NAME}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    elif system == "Linux":
        subprocess.Popen(
            ["systemctl", "--user", "start", APP_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    elif system == "Windows":
        import msvcrt  # type: ignore
        try:
            fh = open(_LOCK_FILE, "w")
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            fh.close()
            # Lock acquired → nobody running, safe to start.
        except OSError:
            return  # already running
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            [sys.executable],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )


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

