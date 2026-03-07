#!/usr/bin/env python3
"""Simple real-time UDP logger.

Usage:
    python3 udp_logger.py --host 0.0.0.0 --port 5005
"""

from __future__ import annotations

import argparse
import datetime as dt
import signal
import socket
import sys
from typing import Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time UDP logger")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5005, help="Bind port (default: 5005)")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=4096,
        help="Maximum UDP datagram size to read (default: 4096)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print payload as repr(bytes) instead of UTF-8 text",
    )
    return parser.parse_args()


def format_payload(data: bytes, raw: bool) -> str:
    if raw:
        return repr(data)
    return data.decode("utf-8", errors="replace")


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


def main() -> int:
    args = parse_args()

    if not (1 <= args.port <= 65535):
        print("Error: --port must be between 1 and 65535", file=sys.stderr)
        return 2

    running = True

    def stop_handler(_signum: int, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(0.5)

    print(f"[{now_iso()}] Listening UDP on {args.host}:{args.port}", flush=True)

    try:
        while running:
            try:
                data, addr = sock.recvfrom(args.max_bytes)
            except socket.timeout:
                continue

            host, port = cast_addr(addr)
            payload = format_payload(data, args.raw)
            print(
                f"[{now_iso()}] {host}:{port} ({len(data)} bytes) -> {payload}",
                flush=True,
            )
    finally:
        sock.close()
        print(f"[{now_iso()}] UDP logger stopped", flush=True)

    return 0


def cast_addr(addr: Tuple[str, int]) -> Tuple[str, int]:
    # Help static type checkers and keep unpacking explicit.
    return addr[0], addr[1]


if __name__ == "__main__":
    raise SystemExit(main())

