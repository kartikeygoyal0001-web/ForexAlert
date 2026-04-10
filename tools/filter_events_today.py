#!/usr/bin/env python3
"""
filter_events_today.py — WAT Framework Tool
Filters the raw FF event list to today's HIGH IMPACT events only.

Reads:  .tmp/ff_events_raw.json
Writes: .tmp/ff_events_today.json

The FF endpoint returns times in US/Eastern. This script converts them to UTC
and filters for events where date == today (UTC).

Usage:
    python tools/filter_events_today.py
    python tools/filter_events_today.py --date 2026-04-10   # override date for testing

Exit codes:
    0 — success (even if 0 events — check clear_day flag in output)
    1 — input file missing or unreadable
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS

UTC = timezone.utc


def parse_ff_datetime(event: dict) -> datetime | None:
    """
    Parse the FF endpoint's date field into a UTC datetime.
    The endpoint returns ISO 8601 datetime strings with timezone offset,
    e.g. "2026-04-10T08:30:00-04:00".
    Returns None if parsing fails.
    """
    date_str = event.get("date", "").strip()
    if not date_str:
        return None

    # Try ISO 8601 with timezone offset (real endpoint format)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z"):
        try:
            dt = datetime.strptime(date_str[:25], fmt)  # handle variable tz offsets
            return dt.astimezone(UTC)
        except ValueError:
            pass

    # Fallback: try parsing without timezone
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            pass

    return None


def today_utc_date(override: str | None) -> str:
    """Return today's date as YYYY-MM-DD in UTC, or use override."""
    if override:
        return override
    return datetime.now(UTC).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter FF events to today's high-impact events."
    )
    parser.add_argument("--input", default=PATHS["ff_raw"], help="Raw events JSON path")
    parser.add_argument("--output", default=PATHS["ff_today"], help="Filtered output JSON path")
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD) for testing")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"Input file not found: {args.input}"}), file=sys.stderr)
        sys.exit(1)

    raw_events: list[dict] = json.loads(input_path.read_text(encoding="utf-8"))
    target_date = today_utc_date(args.date)
    print(f"[filter] Filtering for date: {target_date} (UTC), impact: High", flush=True)

    filtered = []
    for ev in raw_events:
        impact = ev.get("impact", "").strip()
        if impact.lower() != "high":
            continue

        utc_dt = parse_ff_datetime(ev)
        if utc_dt:
            event_date = utc_dt.strftime("%Y-%m-%d")
            ev["time_utc"] = utc_dt.strftime("%H:%M")
        else:
            # Last resort: try to parse date portion of the raw string
            raw_date = ev.get("date", "")
            try:
                event_date = raw_date[:10]  # "YYYY-MM-DD"
            except Exception:
                event_date = ""
            ev["time_utc"] = ""

        if event_date == target_date:
            filtered.append(ev)

    clear_day = len(filtered) == 0
    output = {
        "date": target_date,
        "clear_day": clear_day,
        "event_count": len(filtered),
        "events": filtered,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")

    if clear_day:
        print(f"[filter] No high-impact events today ({target_date}) — clear_day=true", flush=True)
    else:
        print(f"[filter] Found {len(filtered)} high-impact event(s) for {target_date}", flush=True)
        for ev in filtered:
            print(f"  {ev.get('time_utc')} UTC | {ev.get('country')} | {ev.get('title')}", flush=True)

    print(json.dumps({
        "status": "ok",
        "date": target_date,
        "clear_day": clear_day,
        "event_count": len(filtered),
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
