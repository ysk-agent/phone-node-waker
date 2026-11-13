#!/usr/bin/env python3
"""TCP relay for adb over the Muse VM's Tailscale tunnel proxy.

Listens on 127.0.0.1:<local_port>; for each accepted connection it
issues an HTTP CONNECT through the runtime tunnel proxy (HTTPS_PROXY
host, port 3130 — the same route tailscale_connect.py uses for SSH)
to <target_host>:<target_port> and relays bytes both ways.

Usage: adb_relay.py <local_port> <target_host> <target_port>
"""
import base64
import os
import socket
import sys
import threading
from urllib.parse import unquote, urlparse


def open_tunnel(target_host: str, target_port: int) -> socket.socket:
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not raw:
        raise RuntimeError("HTTPS_PROXY is not set")
    parsed = urlparse(raw)
    sock = socket.create_connection((parsed.hostname, 3130), timeout=20)
    lines = [
        f"CONNECT {target_host}:{target_port} HTTP/1.1",
        f"Host: {target_host}:{target_port}",
    ]
    if parsed.username:
        token = base64.b64encode(
            f"{unquote(parsed.username)}:{unquote(parsed.password or '')}".encode()
        ).decode()
        lines.append(f"Proxy-Authorization: Basic {token}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    if " 200" not in status:
        sock.close()
        raise RuntimeError(f"CONNECT failed: {status}")
    if rest:
        sock.settimeout(1)
        # Push back any already-read bytes by wrapping: caller handles via prebuffer.
        sock._prebuffer = rest  # type: ignore[attr-defined]
    sock.settimeout(None)
    return sock


def pump(src: socket.socket, dst: socket.socket, pre: bytes = b"") -> None:
    try:
        if pre:
            dst.sendall(pre)
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    try:
        dst.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def handle(client: socket.socket, target_host: str, target_port: int) -> None:
    try:
        remote = open_tunnel(target_host, target_port)
    except Exception as e:
        print(f"tunnel error: {e}", file=sys.stderr)
        client.close()
        return
    pre = getattr(remote, "_prebuffer", b"")
    t = threading.Thread(target=pump, args=(client, remote), daemon=True)
    t.start()
    pump(remote, client, pre)
    client.close()
    remote.close()


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    local_port, target_host, target_port = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", local_port))
    server.listen(5)
    print(f"relay 127.0.0.1:{local_port} -> {target_host}:{target_port}", flush=True)
    while True:
        client, _ = server.accept()
        threading.Thread(
            target=handle, args=(client, target_host, target_port), daemon=True
        ).start()


if __name__ == "__main__":
    raise SystemExit(main())
