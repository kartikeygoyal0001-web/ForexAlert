#!/usr/bin/env python3
"""
fetch_ff_events.py — WAT Framework Tool
Fetches this week's economic calendar from Forex Factory.

Primary:  nfs.faireconomy.media/ff_calendar_thisweek.json
Fallback: JBlanked Calendar API (today's high-impact events)

Usage:
    python tools/fetch_ff_events.py
    python tools/fetch_ff_events.py --output .tmp/ff_events_raw.json
    python tools/fetch_ff_events.py --timeout 15

Exit codes:
    0 — success, events written to output file
    1 — both primary and fallback failed (fatal)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import FF_ENDPOINT, JBLANKED_ENDPOINT, PATHS

load_dotenv()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_primary(timeout: int) -> list[dict]:
    """Fetch from the official FF JSON export endpoint."""
    print(f"[fetch] Trying primary: {FF_ENDPOINT}", flush=True)
    resp = requests.get(FF_ENDPOINT, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response format: {type(data)}")
    print(f"[fetch] Primary OK — {len(data)} events this week", flush=True)
    return data


def fetch_jblanked_fallback() -> list[dict]:
    """
    Fallback: JBlanked API — today's high-impact events only.
    Returns events normalized to the same schema as the FF endpoint.
    """
    print(f"[fetch] Trying JBlanked fallback: {JBLANKED_ENDPOINT}", flush=True)
    resp = requests.get(JBLANKED_ENDPOINT, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # JBlanked returns a different schema — normalize it
    normalized = []
    events = data if isinstance(data, list) else data.get("events", [])
    for ev in events:
        normalized.append({
            "title":    ev.get("name") or ev.get("title", ""),
            "country":  ev.get("currency") or ev.get("country", ""),
            "date":     ev.get("date", ""),
            "time":     ev.get("time", ""),
            "impact":   "High",
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "actual":   ev.get("actual", ""),
        })
    print(f"[fetch] JBlanked OK — {len(normalized)} high-impact events", flush=True)
    return normalized


def send_admin_alert(message: str) -> None:
    """Log admin alert to stderr (email escalation handled by run_morning_alert.py)."""
    print(f"[ADMIN ALERT] {message}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Forex Factory economic calendar events.")
    parser.add_argument("--output", default=PATHS["ff_raw"], help="Output JSON file path")
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("FF_ENDPOINT_TIMEOUT", "10")),
        help="HTTP timeout in seconds for primary endpoint",
    )
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []

    # --- Primary ---
    try:
        events = fetch_primary(args.timeout)
    except Exception as primary_exc:
        print(f"[fetch] Primary failed: {primary_exc}", file=sys.stderr)
        print("[fetch] Waiting 5s before fallback...", flush=True)
        time.sleep(5)

        # --- Fallback ---
        try:
            events = fetch_jblanked_fallback()
        except Exception as fallback_exc:
            print(f"[fetch] Fallback also failed: {fallback_exc}", file=sys.stderr)
            send_admin_alert(
                f"BOTH data sources failed. Primary: {primary_exc} | Fallback: {fallback_exc}"
            )
            print(json.dumps({
                "error": "All data sources failed",
                "primary_error": str(primary_exc),
                "fallback_error": str(fallback_exc),
            }), file=sys.stderr)
            sys.exit(1)

    Path(args.output).write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "event_count": len(events),
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
