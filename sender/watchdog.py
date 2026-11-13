#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Watchdog for the Libero phone-node: check the opencode serve health
through the tailnet tunnel; when it is down (and the route itself is
fine), send an FCM wake via send_wake.py and verify recovery.

Run by the cron job `libero-node-watchdog`; can also be run by hand.

Outcomes (printed as the last line, WATCHDOG_RESULT: <name>):
  healthy          serve answered 200; nothing to do
  route_down       neither Libero nor moto answered: the VM's tunnel
                   route is suspect, NOT the node; no FCM sent
  cooldown_skip    node down but a wake was successfully sent < 20 min
                   ago (a failed send does NOT start the cooldown, so
                   the next cycle retries; a token_stale outcome DOES,
                   because it would fail identically every cycle)
  sent_recovered   FCM sent and health returned within ~90 s
  sent_unverified  FCM sent (HTTP 200) but health not back in ~90 s
  token_stale      FCM returned UNREGISTERED: the stored device token
                   was superseded; a fresh token must be captured
  send_failed      the send itself failed; the FULL send_wake output
                   (including any traceback) is in the log
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "watchdog-state.json")
LOG_PATH = os.path.join(HERE, "watchdog.log")
SA_KEY = os.path.expanduser("~/workspace/.secrets/nodewaker-sa.json")
TOKEN_PATH = os.path.expanduser("~/workspace/.secrets/waker-token-libero.txt")
SEND_WAKE = os.path.join(HERE, "send_wake.py")
UV = "/home/hatch/.local/bin/uv"

LIBERO_HEALTH = "http://100.103.150.123:4096/global/health"
MOTO_HEALTH = "http://100.102.129.64:4096/global/health"
COOLDOWN_SECS = 20 * 60


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S %Z')} {msg}"
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def tunnel_proxy() -> str:
    raw = os.environ.get("HTTPS_PROXY", "")
    host = raw.rsplit("@", 1)[-1].rsplit(":", 1)[0]
    return f"http://{host}:3130"


def healthy(url: str) -> bool:
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-m", "10", "-w", "%{http_code}",
             "--proxy", tunnel_proxy(), url],
            capture_output=True, text=True, timeout=15,
        )
        return out.stdout.strip() == "200"
    except Exception:
        return False


def load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def send_wake() -> tuple[int, str]:
    token = open(TOKEN_PATH).read().strip()
    out = subprocess.run(
        [UV, "run", "--no-project", "--with", "cryptography", "python3",
         SEND_WAKE, "--key", SA_KEY, "--token", token],
        capture_output=True, text=True, timeout=90,
    )
    return out.returncode, (out.stdout + out.stderr)


def main() -> int:
    state = load_state()
    now = time.time()

    if healthy(LIBERO_HEALTH):
        if state.get("episode"):
            state["episode"] = False
            save_state(state)
        log("healthy")
        print("WATCHDOG_RESULT: healthy")
        return 0

    time.sleep(20)
    if healthy(LIBERO_HEALTH):
        log("healthy on confirm probe (transient)")
        print("WATCHDOG_RESULT: healthy")
        return 0

    # Libero down twice. Is the route itself down? Probe a second node.
    if not healthy(MOTO_HEALTH):
        first = not state.get("episode")
        state["episode"] = True
        save_state(state)
        log("route_down (both Libero and moto unreachable)")
        print("WATCHDOG_RESULT: route_down" + (" first" if first else " ongoing"))
        return 0

    last_send = state.get("last_send_epoch", 0)
    if now - last_send < COOLDOWN_SECS:
        log(f"node down, cooldown skip ({int(now - last_send)}s since last send)")
        print("WATCHDOG_RESULT: cooldown_skip")
        return 0

    code, out = send_wake()
    # Log the FULL output. The previous [:200] truncation cut the
    # 2026-11-14 06:30 traceback before its root line, which made that
    # send_failed undiagnosable from the log alone.
    log(f"send_wake rc={code} out={out.strip()!r}")

    if "UNREGISTERED" in out:
        # A stale token fails identically on every retry, so this
        # outcome DOES start the cooldown (otherwise the fresh-token
        # request would repeat every cycle).
        state["last_send_epoch"] = time.time()
        save_state(state)
        print("WATCHDOG_RESULT: token_stale")
        return 0
    if code != 0:
        # A failed send woke nothing, so it must NOT start the
        # cooldown: the next cycle retries instead of waiting 20 min
        # (Moriya's fix request, 2026-11-14, after the 06:30 failure
        # was masked by the cooldown it had consumed).
        print("WATCHDOG_RESULT: send_failed")
        return 0

    # Only a successful send starts the cooldown.
    state["last_send_epoch"] = time.time()
    save_state(state)

    for _ in range(6):
        time.sleep(15)
        if healthy(LIBERO_HEALTH):
            log("recovered after FCM wake")
            print("WATCHDOG_RESULT: sent_recovered")
            return 0
    log("sent but not recovered within ~90s")
    print("WATCHDOG_RESULT: sent_unverified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
