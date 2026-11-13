#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "cryptography"]
# ///
"""Send a high-priority FCM data message {action: wake} to a phone-node
waker app, using the FCM HTTP v1 API with a service-account key.

Usage:
    uv run send_wake.py --key /path/to/service-account.json --token <device token>
    uv run send_wake.py --key ... --token ... --dry-run   # build + sign only, no network

The service-account JSON is a credential: keep it out of git and chat.
The device token is shown in the waker app's UI on the phone.
"""
import argparse
import base64
import json
import sys
import time

import httpx
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


def get_access_token(sa: dict) -> str:
    jwt = build_jwt(sa)
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


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
    resp = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
