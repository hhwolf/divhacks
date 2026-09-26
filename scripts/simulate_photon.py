#!/usr/bin/env python3
"""Post each fixtures/photon/*.json to the local webhook and print the reply.

Usage: .venv/bin/python scripts/simulate_photon.py [--url http://localhost:8000/webhooks/photon] [--only text-question]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "photon"


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
        resp = httpx.post(args.url, json=payload, timeout=30)
        body = resp.json()
        print(f"<- {resp.status_code} {body.get('reply')}")
        if body.get("layoutId"):
            print(f"   layout {body['layoutId']}  links: {', '.join((body.get('outbound') or {}).get('links', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
