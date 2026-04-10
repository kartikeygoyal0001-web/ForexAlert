#!/usr/bin/env python3
"""
generate_event_analysis.py — WAT Framework Tool
Calls OpenAI gpt-4o to generate structured analysis for ONE economic event.
Optionally accepts live news context (from fetch_event_news.py) to ground the analysis
in today's actual market narrative rather than purely training-data knowledge.

Usage:
    python tools/generate_event_analysis.py --event-json '{"title":"Core CPI m/m","country":"USD",...}'
    python tools/generate_event_analysis.py --event-json '...' --news-context '{"combined_text":"..."}'

Exit codes:
    0 — success, JSON analysis printed to stdout
    1 — missing/invalid arguments
    2 — OpenAI API error (after retries)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CURRENCY_TO_INSTRUMENTS

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# JSON output schema — tells the model exactly what fields to return
# ──────────────────────────────────────────────────────────────────────────────
ANALYSIS_SCHEMA = {
    "event_name": "Short plain-English event name (e.g. 'US Core CPI m/m')",
    "plain_explanation": (
        "2-3 sentences. What this indicator measures, why central banks and traders watch it, "
        "and what direction is considered 'strong' for the currency. Assume the reader is a "
        "self-taught retail trader with 1-2 years of experience."
    ),
    "historical_context": (
        "What happened at the most recent release and the 3-release trend. "
        "Example: 'March came in at 0.2%, below the 0.3% forecast — the third consecutive miss. "
        "Inflation is clearly decelerating.' Use the previous value from the event data."
    ),
    "forecast_vs_previous": (
        "Plain comparison of forecast vs previous. Describe the direction and magnitude. "
        "Example: 'Forecast of 0.3% is slightly above the previous 0.2%, suggesting analysts "
        "expect mild re-acceleration. A beat would reinforce hawkish Fed expectations.'"
    ),
    "affected_instruments": [
        "EURUSD",
        "(list only the instruments from the provided list that are most directly impacted — "
        "typically 3-6 pairs; do not include pairs with indirect or negligible exposure)"
    ],
    "bullish_scenario": (
        "What happens if data BEATS forecast. Name specific pairs and direction. "
        "Example: 'USD strengthens — EURUSD drops toward 1.0800 support, XAUUSD sells off "
        "as rate-hike expectations rise. GBPUSD likely follows EURUSD lower.'"
    ),
    "bearish_scenario": (
        "What happens if data MISSES forecast. Name specific pairs and direction. "
        "Example: 'USD weakens — EURUSD reclaims 1.0950, XAUUSD spikes toward 2350 as "
        "rate-cut narrative gains. Risk-on tone benefits AUD and NZD.'"
    ),
    "trading_note": (
        "One concrete, actionable sentence. Focus on timing, key levels, or risk management. "
        "Example: 'Watch the 13:30 UTC candle close — first 15 minutes often see a fake spike "
        "before the real direction sets in; wait for a confirmed close before entering.'"
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# System prompt — the OpenAI model's full briefing
# See workflows/openai_model_instructions.md for the detailed rationale
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the analysis engine for an automated Forex Factory Morning Alert system.

## Your Role
You are a professional forex market analyst and trading educator. Your job is to analyze
high-impact economic events and produce structured, actionable briefings for retail forex traders.
You are part of a fully automated pipeline — your output is parsed by code, not read by a human.
This means you must return ONLY valid JSON with the exact schema requested. Never include
markdown, code blocks, explanatory text, or any content outside the JSON object.

## Who the End Users Are
Retail forex traders who:
- Trade instruments like EURUSD, XAUUSD, GBPUSD
- Have 1-3 years of experience — they understand pips, support/resistance, and basic fundamentals
- Need plain-English explanations, not academic language
- Want to know: what this event is, what the market expects, and what to DO if it beats or misses
- Check this briefing at 06:30 UTC before the trading session opens

## Output Quality Standards

### plain_explanation
- Do NOT use jargon like "monetary aggregates", "non-seasonally adjusted", or "index rebasing"
- DO explain why this number matters to central bank policy and therefore to currency value
- Length: 2-3 sentences. Dense, not fluffy.

### historical_context
- Ground this in the PREVIOUS value from the event data you are given
- If news context is provided, use it to describe the actual recent trend
- If no news context is provided, use your training knowledge about the indicator's recent history
- Be specific: "third consecutive miss" is better than "recent weakness"

### forecast_vs_previous
- Always state whether forecast is higher, lower, or in-line with previous
- Explain what that direction means for rate expectations and the currency
- One paragraph, 2-3 sentences

### affected_instruments
- Only list instruments from the explicitly provided list
- Prioritize direct exposure: USD event → EURUSD first, then GBPUSD, then XAUUSD (as USD-denominated commodity)
- Do NOT list instruments with indirect or negligible exposure
- Typical count: 3-6 instruments

### bullish_scenario / bearish_scenario
- Always frame from the EVENT CURRENCY's perspective (USD event → bullish = USD strength)
- Name specific pairs and the likely directional move
- Include a key price level or area if you know one (e.g. "1.0800 support")
- Length: 1-2 sentences each

### trading_note
- One sentence. Concrete and time-specific.
- Focus on: entry timing, key level to watch, or risk management around the release
- Avoid generic advice like "be careful" or "watch for volatility"

## How to Handle Missing Data
- Forecast is N/A: Acknowledge market participants are watching for the direction vs previous
- Actual is "Not yet released": Write scenarios for beat/miss vs forecast (not vs actual)
- Previous is N/A: Describe the event in isolation; note data unavailability

## If News Context Is Provided
Use it to:
1. Ground historical_context in what analysts are actually saying today
2. Reference specific themes (e.g. "analysts cite sticky shelter costs as the upside risk")
3. Incorporate market positioning if mentioned ("market is pricing in a 0.3% print")
Do not fabricate quotes. Paraphrase, summarize, and synthesize.

## JSON Contract
Return ONLY the JSON object. No markdown. No code fences. No commentary. No trailing text.
The exact keys are specified in the user message. Missing keys cause downstream failures."""


# ──────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ──────────────────────────────────────────────────────────────────────────────

def build_user_prompt(event: dict, instruments: list[str], news_context: dict | None) -> str:
    news_section = ""
    if news_context:
        text = news_context.get("combined_text", "").strip()
        source = news_context.get("source", "unknown")
        if text:
            news_section = f"""
## Live Market Context (from {source} — fetched today)
The following analyst commentary and news was retrieved this morning about this specific event.
Use it to ground your historical_context and forecast_vs_previous in today's narrative:

{text[:2500]}

--- End of live context ---
"""

    return f"""Analyze this economic event for the Forex Morning Alert system:

## Event Data
Event: {event.get("title", "Unknown")}
Currency: {event.get("country", "Unknown")}
Scheduled release: {event.get("time_utc", event.get("time", "TBD"))} UTC today
Forecast: {event.get("forecast") or "N/A"}
Previous: {event.get("previous") or "N/A"}
Actual: {event.get("actual") or "Not yet released"}
{news_section}
## Instruments to consider (choose the most affected):
{", ".join(instruments)}

## Required JSON output schema:
{json.dumps(ANALYSIS_SCHEMA, indent=2)}

Return ONLY the JSON object with exactly these keys. Do not include any text outside the JSON."""


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI call
# ──────────────────────────────────────────────────────────────────────────────

def call_openai(prompt: str, api_key: str, retry: bool = False) -> str:
    from openai import OpenAI, RateLimitError, APIError

    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.2,          # low temp = precise, structured output
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content.strip()

    except RateLimitError as exc:
        if not retry:
            print("[analysis] Rate limited — sleeping 30s then retrying...", file=sys.stderr)
            time.sleep(30)
            return call_openai(prompt, api_key, retry=True)
        print(json.dumps({"error": f"Rate limit after retry: {exc}"}), file=sys.stderr)
        sys.exit(2)

    except APIError as exc:
        if not retry:
            print(f"[analysis] API error — retrying once: {exc}", file=sys.stderr)
            time.sleep(5)
            return call_openai(prompt, api_key, retry=True)
        print(json.dumps({"error": f"OpenAI API error: {exc}"}), file=sys.stderr)
        sys.exit(2)


def build_raw_fallback(event: dict, instruments: list[str]) -> dict:
    """Used when OpenAI analysis fails — returns minimal usable content."""
    title = event.get("title", "Unknown Event")
    country = event.get("country", "")
    forecast = event.get("forecast") or "N/A"
    previous = event.get("previous") or "N/A"
    return {
        "event_name": f"{country} {title}",
        "plain_explanation": (
            f"{title} is a key economic indicator for {country}. "
            "AI analysis is temporarily unavailable — refer to the forecast and previous values."
        ),
        "historical_context": f"Previous release: {previous}. Current forecast: {forecast}.",
        "forecast_vs_previous": f"Forecast: {forecast} | Previous: {previous}",
        "affected_instruments": instruments[:5],
        "bullish_scenario": f"Data beats forecast ({forecast}): {country} currency likely strengthens.",
        "bearish_scenario": f"Data misses forecast ({forecast}): {country} currency likely weakens.",
        "trading_note": "Monitor price action at the scheduled release time. Wait for the initial spike to settle before entering.",
        "_fallback": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OpenAI analysis for one FF event.")
    parser.add_argument("--event-json", required=True, help="JSON string of the event object")
    parser.add_argument("--news-context", default=None,
                        help="JSON string with news context for this event (optional)")
    args = parser.parse_args()

    try:
        event = json.loads(args.event_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid --event-json: {exc}"}), file=sys.stderr)
        sys.exit(1)

    news_context = None
    if args.news_context:
        try:
            news_context = json.loads(args.news_context)
        except json.JSONDecodeError:
            print("[analysis] WARNING: Could not parse --news-context — proceeding without it",
                  file=sys.stderr)

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-YOUR"):
        print(json.dumps({
            "error": "OPENAI_API_KEY not set",
            "fix": "Add OPENAI_API_KEY=sk-... to your .env file",
        }), file=sys.stderr)
        sys.exit(2)

    country = event.get("country", "").upper()
    instruments = CURRENCY_TO_INSTRUMENTS.get(country, [])

    has_news = bool(news_context and news_context.get("combined_text"))
    print(
        f"[analysis] Analyzing: {event.get('title')} ({country}) "
        f"{'[+news context]' if has_news else '[no news context]'} ...",
        file=sys.stderr, flush=True,
    )

    prompt = build_user_prompt(event, instruments, news_context)
    raw_json = call_openai(prompt, api_key)

    try:
        analysis = json.loads(raw_json)
    except json.JSONDecodeError:
        print("[analysis] JSON parse failed - retrying with strict instruction...", file=sys.stderr)
        strict_prompt = (
            prompt
            + "\n\nCRITICAL: Your previous response was not valid JSON. "
            "Return ONLY the JSON object. No markdown. No code blocks. Start with { and end with }."
        )
        raw_json2 = call_openai(strict_prompt, api_key)
        try:
            analysis = json.loads(raw_json2)
        except json.JSONDecodeError:
            print("[analysis] Second parse failed — using fallback", file=sys.stderr)
            analysis = build_raw_fallback(event, instruments)

    result = {**event, "analysis": analysis}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
