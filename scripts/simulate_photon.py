#!/usr/bin/env python3
"""Post each fixtures/photon/*.json to the local webhook and print the reply.

Usage: .venv/bin/python scripts/simulate_photon.py [--url http://localhost:8000/webhooks/photon] [--only text-question]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import hashlib
import hmac
import os
import time

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "photon"


ROOT = Path(__file__).resolve().parents[1]


def signed_headers(raw: bytes) -> dict[str, str]:
    """Spectrum-style v0 signature when PHOTON_WEBHOOK_SECRET is set (env or repo .env); the API rejects unsigned calls then."""
    secret = os.environ.get("PHOTON_WEBHOOK_SECRET", "")
    env = ROOT / ".env"
    if not secret and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("PHOTON_WEBHOOK_SECRET="):
                secret = line.split("=", 1)[1].split("#", 1)[0].strip().strip('"')
    if not secret:
        return {}
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"v0:{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return {"X-Spectrum-Timestamp": ts, "X-Spectrum-Signature": f"v0={sig}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://localhost:8000/webhooks/photon")
    ap.add_argument("--only", help="fixture name without .json")
    args = ap.parse_args()
    paths = sorted(FIXTURES.glob(f"{args.only or '*'}.json"))
    if not paths:
        print(f"no fixture matches {args.only!r} in {FIXTURES}", file=sys.stderr)
        return 1
    for path in paths:
        payload = json.loads(path.read_text())
        print(f"-> {path.stem}: {payload['message']['text']}")
        raw = json.dumps(payload).encode()
        resp = httpx.post(args.url, content=raw, headers={"Content-Type": "application/json", **signed_headers(raw)}, timeout=30)
        body = resp.json()
        print(f"<- {resp.status_code} {body.get('reply')}")
        if body.get("layoutId"):
            print(f"   layout {body['layoutId']}  links: {', '.join((body.get('outbound') or {}).get('links', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
