#!/usr/bin/env python3
"""
generate_all_analyses.py — WAT Framework Tool
Reads today's filtered events and calls generate_event_analysis.py for each one.
Loads event_news_context.json (if available) and passes per-event news context
to the analysis tool for grounded, news-enriched AI output.
Writes the merged results to .tmp/analyses.json.

Usage:
    python tools/generate_all_analyses.py
    python tools/generate_all_analyses.py --input .tmp/ff_events_today.json

Exit codes:
    0 — success (analyses.json written, even if some events used fallback)
    1 — input file missing or no events to analyze
    2 — fatal error
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS

TOOL = Path(__file__).parent / "generate_event_analysis.py"
SLEEP_BETWEEN = 1  # seconds between API calls


def load_news_context(news_path: str) -> dict:
    """Load event_news_context.json. Returns empty dict if missing — news is optional."""
    path = Path(news_path)
    if not path.exists():
        print(f"[analyses] No news context file found at {news_path} — proceeding without enrichment",
              flush=True)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events", {})
        source = payload.get("source", "none")
        if events and source != "none":
            total_snippets = sum(len(v.get("snippets", [])) for v in events.values())
            print(f"[analyses] News context loaded: {len(events)} event(s), "
                  f"{total_snippets} snippet(s) via {source}", flush=True)
        else:
            print("[analyses] News context file present but empty — proceeding without enrichment",
                  flush=True)
        return events
    except Exception as exc:
        print(f"[analyses] WARNING: Could not load news context: {exc}", file=sys.stderr)
        return {}


def event_key(event: dict) -> str:
    """Match the key format used in fetch_event_news.py."""
    return f"{event.get('title', 'unknown')}_{event.get('country', 'XX')}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze all of today's high-impact events via OpenAI."
    )
    parser.add_argument("--input", default=PATHS["ff_today"], help="Filtered events JSON path")
    parser.add_argument("--output", default=PATHS["analyses"], help="Output analyses JSON path")
    parser.add_argument("--news-context", default=PATHS["news_context"],
                        help="News context JSON path (from fetch_event_news.py)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"Input not found: {args.input}"}), file=sys.stderr)
        sys.exit(1)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("clear_day"):
        print("[analyses] Clear day — nothing to analyze", flush=True)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps({"clear_day": True, "analyses": []}, indent=2), encoding="utf-8"
        )
        print(json.dumps({"status": "ok", "clear_day": True, "event_count": 0}))
        return

    events = payload.get("events", [])
    if not events:
        print(json.dumps({"error": "No events found in input file"}), file=sys.stderr)
        sys.exit(1)

    # Load news context (non-fatal if missing)
    news_contexts = load_news_context(args.news_context)

    print(f"[analyses] Analyzing {len(events)} event(s)...", flush=True)
    analyses = []

    for i, event in enumerate(events, start=1):
        title = event.get("title", "Unknown")
        key = event_key(event)
        print(f"[analyses] [{i}/{len(events)}] {title}", flush=True)

        # Build subprocess args
        cmd = [sys.executable, str(TOOL), "--event-json", json.dumps(event)]

        # Attach news context for this event if available
        event_news = news_contexts.get(key)
        if event_news and event_news.get("combined_text"):
            cmd += ["--news-context", json.dumps(event_news)]
            print(f"[analyses]   (news context: {len(event_news.get('snippets', []))} snippet(s))",
                  flush=True)

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(
                f"[analyses] WARNING: Analysis failed for '{title}': {result.stderr.strip()}",
                file=sys.stderr,
            )
            analyses.append({**event, "analysis": None, "_error": result.stderr.strip()[:200]})
        else:
            try:
                data = json.loads(result.stdout)
                analyses.append(data)
                event_name = data.get("analysis", {}).get("event_name", title) if data.get("analysis") else title
                fallback_tag = " [FALLBACK]" if data.get("analysis", {}).get("_fallback") else ""
                print(f"[analyses]   -> OK: {event_name}{fallback_tag}", flush=True)
            except json.JSONDecodeError:
                print(f"[analyses] WARNING: Could not parse output for '{title}'", file=sys.stderr)
                analyses.append({**event, "analysis": None})

        if i < len(events):
            time.sleep(SLEEP_BETWEEN)

    output = {
        "date": payload.get("date"),
        "clear_day": False,
        "event_count": len(analyses),
        "news_source": json.loads(
            Path(args.news_context).read_text(encoding="utf-8")
        ).get("source", "none") if Path(args.news_context).exists() else "none",
        "analyses": analyses,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")

    fallback_count = sum(
        1 for a in analyses
        if a.get("analysis") is None or (a.get("analysis") or {}).get("_fallback")
    )
    news_enriched = sum(
        1 for a in analyses
        if news_contexts.get(event_key(a)) and news_contexts[event_key(a)].get("combined_text")
    )
    print(
        f"[analyses] Done — {len(analyses)} event(s), "
        f"{news_enriched} news-enriched, {fallback_count} fallback",
        flush=True,
    )
    print(json.dumps({
        "status": "ok",
        "event_count": len(analyses),
        "news_enriched": news_enriched,
        "fallback_count": fallback_count,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
