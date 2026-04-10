#!/usr/bin/env python3
"""
fetch_event_news.py — WAT Framework Tool
Fetches live news/analyst commentary for each of today's high-impact events.

Strategy:
  Primary   → Tavily Search API (fast, structured, purpose-built for AI agents)
  Secondary → Firecrawl Search API (deeper scraping of FXStreet / Reuters / ForexLive)
  Fallback  → Empty context (non-fatal — analysis still runs, just without news grounding)

For each event, searches for analyst previews, market expectations, and key themes.
Writes a combined context block that gets injected into the OpenAI analysis prompt.

Usage:
    python tools/fetch_event_news.py
    python tools/fetch_event_news.py --input .tmp/ff_events_today.json
    python tools/fetch_event_news.py --input .tmp/ff_events_today.json --output .tmp/event_news_context.json

Output schema (.tmp/event_news_context.json):
    {
      "date": "2026-04-10",
      "source": "tavily|firecrawl|none",
      "events": {
        "Core CPI m/m_USD": {
          "title": "Core CPI m/m",
          "country": "USD",
          "snippets": [{"title": "...", "url": "...", "excerpt": "..."}],
          "combined_text": "Full text to inject into prompt"
        }
      }
    }

Exit codes:
    0 — success (even if no news found — news is enrichment, not required)
    1 — input file missing
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS

load_dotenv()

# How many search results per event
TAVILY_MAX_RESULTS = 4
FIRECRAWL_MAX_RESULTS = 3

# Target domains for financial event previews (Tavily include_domains)
FINANCIAL_DOMAINS = [
    "fxstreet.com",
    "forexlive.com",
    "dailyfx.com",
    "reuters.com",
    "marketwatch.com",
    "investing.com",
    "financemagnates.com",
    "action-forex.com",
    "babypips.com",
]


def build_search_query(event: dict) -> str:
    """Build a targeted search query for the event."""
    title = event.get("title", "")
    country = event.get("country", "")
    date = event.get("date", "")[:10] if event.get("date") else ""

    # e.g. "Core CPI m/m USD April 2026 forecast preview analysis"
    date_label = ""
    if date:
        try:
            from datetime import datetime
            dt = datetime.strptime(date, "%Y-%m-%d")
            date_label = dt.strftime("%B %Y")
        except Exception:
            date_label = date

    return f"{title} {country} {date_label} forecast preview market analysis"


def event_key(event: dict) -> str:
    """Unique key for an event: title + currency."""
    return f"{event.get('title', 'unknown')}_{event.get('country', 'XX')}"


# ──────────────────────────────────────────────────────────────────────────────
# Tavily (Primary)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_via_tavily(events: list[dict]) -> dict:
    """
    Use Tavily Search API to get analyst previews for each event.
    Returns dict: event_key → context dict.
    Raises ImportError if tavily-python not installed.
    """
    from tavily import TavilyClient

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key or api_key.startswith("tvly-YOUR"):
        raise ValueError("TAVILY_API_KEY not set")

    client = TavilyClient(api_key=api_key)
    results: dict = {}

    for i, event in enumerate(events):
        key = event_key(event)
        query = build_search_query(event)
        print(f"[news/tavily] [{i+1}/{len(events)}] {event.get('title')} ...", flush=True)

        try:
            response = client.search(
                query=query,
                max_results=TAVILY_MAX_RESULTS,
                search_depth="advanced",
                include_domains=FINANCIAL_DOMAINS,
                include_answer=True,  # Tavily's AI-generated answer from search results
            )

            snippets = []
            for r in response.get("results", []):
                excerpt = (r.get("content") or "").strip()
                if len(excerpt) > 600:
                    excerpt = excerpt[:600] + "..."
                snippets.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "excerpt": excerpt,
                })

            # Tavily's synthesized answer (if available) goes first
            ai_answer = response.get("answer", "")
            combined_parts = []
            if ai_answer:
                combined_parts.append(f"Market consensus summary: {ai_answer}")
            for s in snippets:
                if s["excerpt"]:
                    combined_parts.append(f"[{s['title']}] {s['excerpt']}")

            combined_text = "\n\n".join(combined_parts)

            results[key] = {
                "title": event.get("title"),
                "country": event.get("country"),
                "snippets": snippets,
                "combined_text": combined_text,
                "source": "tavily",
            }
            print(f"[news/tavily]   -> {len(snippets)} result(s)", flush=True)

        except Exception as exc:
            print(f"[news/tavily] WARNING: Search failed for '{event.get('title')}': {exc}",
                  file=sys.stderr)
            results[key] = _empty_context(event)

        if i < len(events) - 1:
            time.sleep(0.5)  # be gentle with rate limits

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Firecrawl (Secondary)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_via_firecrawl(events: list[dict]) -> dict:
    """
    Use Firecrawl Search API to find and extract news pages per event.
    Returns dict: event_key → context dict.
    Raises ImportError if firecrawl-py not installed, ValueError if no API key.
    """
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key or api_key.startswith("fc-YOUR"):
        raise ValueError("FIRECRAWL_API_KEY not set")

    app = FirecrawlApp(api_key=api_key)
    results: dict = {}

    for i, event in enumerate(events):
        key = event_key(event)
        query = build_search_query(event)
        print(f"[news/firecrawl] [{i+1}/{len(events)}] {event.get('title')} ...", flush=True)

        try:
            # Firecrawl search returns pages with extracted markdown content
            response = app.search(
                query=query,
                limit=FIRECRAWL_MAX_RESULTS,
                scrape_options={"formats": ["markdown"]},
            )

            snippets = []
            for r in (response.get("data") or []):
                content = r.get("markdown") or r.get("content") or ""
                # Trim to a useful length
                if len(content) > 800:
                    content = content[:800] + "..."
                title = r.get("metadata", {}).get("title") or r.get("title") or ""
                url = r.get("url") or r.get("metadata", {}).get("url") or ""
                if content:
                    snippets.append({
                        "title": title,
                        "url": url,
                        "excerpt": content.strip(),
                    })

            combined_text = "\n\n".join(
                f"[{s['title']}] {s['excerpt']}" for s in snippets if s["excerpt"]
            )

            results[key] = {
                "title": event.get("title"),
                "country": event.get("country"),
                "snippets": snippets,
                "combined_text": combined_text,
                "source": "firecrawl",
            }
            print(f"[news/firecrawl]   -> {len(snippets)} page(s) scraped", flush=True)

        except Exception as exc:
            print(f"[news/firecrawl] WARNING: Failed for '{event.get('title')}': {exc}",
                  file=sys.stderr)
            results[key] = _empty_context(event)

        if i < len(events) - 1:
            time.sleep(1.0)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _empty_context(event: dict) -> dict:
    return {
        "title": event.get("title"),
        "country": event.get("country"),
        "snippets": [],
        "combined_text": "",
        "source": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch live news context for today's events via Tavily/Firecrawl."
    )
    parser.add_argument("--input", default=PATHS["ff_today"], help="Filtered events JSON path")
    parser.add_argument("--output", default=PATHS["news_context"], help="Output news context JSON path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"Input not found: {args.input}"}), file=sys.stderr)
        sys.exit(1)

    payload = json.loads(input_path.read_text(encoding="utf-8"))

    if payload.get("clear_day"):
        print("[news] Clear day — no events to search for", flush=True)
        output = {"date": payload.get("date"), "source": "none", "events": {}}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "clear_day": True, "events_searched": 0}))
        return

    events = payload.get("events", [])
    if not events:
        print("[news] No events in input — skipping", flush=True)
        output = {"date": payload.get("date"), "source": "none", "events": {}}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "events_searched": 0}))
        return

    print(f"[news] Fetching news context for {len(events)} event(s)...", flush=True)

    # Try Tavily first
    source_used = "none"
    event_contexts: dict = {}

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "")

    if tavily_key and not tavily_key.startswith("tvly-YOUR"):
        try:
            event_contexts = fetch_via_tavily(events)
            source_used = "tavily"
            print(f"[news] Tavily search complete", flush=True)
        except ImportError:
            print("[news] tavily-python not installed — trying Firecrawl", file=sys.stderr)
        except ValueError as exc:
            print(f"[news] Tavily skipped: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[news] Tavily failed: {exc} — trying Firecrawl", file=sys.stderr)

    # Try Firecrawl if Tavily didn't work
    if not event_contexts and firecrawl_key and not firecrawl_key.startswith("fc-YOUR"):
        try:
            event_contexts = fetch_via_firecrawl(events)
            source_used = "firecrawl"
            print(f"[news] Firecrawl search complete", flush=True)
        except ImportError:
            print("[news] firecrawl-py not installed — no news context available", file=sys.stderr)
        except ValueError as exc:
            print(f"[news] Firecrawl skipped: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[news] Firecrawl failed: {exc}", file=sys.stderr)

    # Fill in empties for any events that failed
    for event in events:
        key = event_key(event)
        if key not in event_contexts:
            event_contexts[key] = _empty_context(event)

    if not event_contexts or source_used == "none":
        print("[news] No news context retrieved — analysis will proceed without enrichment", flush=True)

    output = {
        "date": payload.get("date"),
        "source": source_used,
        "events": event_contexts,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    total_snippets = sum(len(v.get("snippets", [])) for v in event_contexts.values())
    print(f"[news] Done — {len(event_contexts)} event(s), {total_snippets} snippet(s) via {source_used}",
          flush=True)
    print(json.dumps({
        "status": "ok",
        "source": source_used,
        "events_searched": len(event_contexts),
        "total_snippets": total_snippets,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
