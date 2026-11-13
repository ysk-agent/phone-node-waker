#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["cryptography"]
# ///
"""Send a high-priority FCM data message {action: wake} to a phone-node
waker app, using the FCM HTTP v1 API with a service-account key.

Usage:
    uv run send_wake.py --key /path/to/service-account.json --token <device token>
    uv run send_wake.py --key ... --token ... --dry-run   # build + sign only, no network

The service-account JSON is a credential: keep it out of git and chat.
The device token is shown in the waker app's UI on the phone.

Transport note (learned the hard way, 2026-11-14): the HTTP calls go
through curl, not httpx. From the Muse VM, httpx crashed on the
bracketed IPv6 entries in NO_PROXY and, with those removed, stalled
indefinitely through the egress proxy, while curl works reliably.
Credentials travel in a mode-600 curl config file, never on the
command line.

Token discipline: FCM registration tokens ROTATE (on reinstall,
data clear, and sometimes spontaneously while a device settles).
FCM answers UNREGISTERED for a superseded token, which looks
exactly like a broken setup. Always send to the freshest token —
the value the waker's Copy button puts on the clipboard (written by
onNewToken) — and if a send returns UNREGISTERED, fetch the token
again before suspecting anything else.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

TOKEN_URL = "https://oauth2.googleapis.com/token"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_jwt(sa: dict) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "scope": FCM_SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(claims).encode())}"
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    signature = key.sign(
        signing_input.encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    return f"{signing_input}.{b64url(signature)}"


def http_post(url: str, *, form: dict | None = None, json_body: dict | None = None,
              bearer: str | None = None) -> tuple[int, str]:
    """POST via curl with a hard 25s cap. Returns (status, body)."""
    cfg_lines = []
    if bearer is not None:
        cfg_lines.append(f'header = "Authorization: Bearer {bearer}"')
    extra: list[str] = []
    if json_body is not None:
        cfg_lines.append('header = "Content-Type: application/json"')
        extra += ["-d", json.dumps(json_body)]
    if form is not None:
        for k, v in form.items():
            extra += ["--data-urlencode", f"{k}={v}"]
    fd, cfg_path = tempfile.mkstemp(prefix="fcm-curl-")
    try:
        with os.fdopen(fd, "w") as f:
            os.chmod(cfg_path, 0o600)
            f.write("\n".join(cfg_lines) + "\n")
        out = subprocess.run(
            ["curl", "-s", "-m", "25", "-K", cfg_path, "-X", "POST", url,
             "-w", "\n%{http_code}"] + extra,
            capture_output=True, text=True, timeout=30,
        )
    finally:
        os.unlink(cfg_path)
    body, _, code = out.stdout.rpartition("\n")
    return int(code or 0), body


def get_access_token(sa: dict) -> str:
    jwt = build_jwt(sa)
    status, body = http_post(
        TOKEN_URL,
        form={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        },
    )
    if status != 200:
        raise RuntimeError(f"token endpoint HTTP {status}: {body[:200]}")
    return json.loads(body)["access_token"]


def build_payload(token: str) -> dict:
    return {
        "message": {
            "token": token,
            "data": {"action": "wake"},
            "android": {"priority": "HIGH"},
        }
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", required=True, help="service-account JSON path")
    ap.add_argument("--token", required=True, help="waker device FCM token")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and sign everything, print the request, send nothing")
    args = ap.parse_args()

    with open(args.key) as f:
        sa = json.load(f)
    project_id = sa["project_id"]
    payload = build_payload(args.token)
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    if args.dry_run:
        jwt = build_jwt(sa)
        print(f"POST {url}")
        print(f"JWT (signed OK, {len(jwt)} chars): {jwt[:40]}...")
        print(json.dumps(payload, indent=2))
        return 0

    access_token = get_access_token(sa)
    status, body = http_post(url, json_body=payload, bearer=access_token)
    print(f"HTTP {status}")
    print(body)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
