#!/usr/bin/env python3
"""
render_email.py — WAT Framework Tool
Renders a personalised HTML email for one subscriber using Jinja2.

Features:
  • "Quick Scan" priority preview at the very top — shows ALL high-impact events
    with times converted to the user's trading timezone so busy traders see the
    full day at a glance without scrolling.
  • Per-event detailed cards below for full analysis.
  • Event times shown in both the user's local timezone and UTC.
  • No PDF attachment — HTML only.

Usage:
    python tools/render_email.py \
        --analyses .tmp/analyses.json \
        --user-json '{"id":1,"name":"Alice","email":"a@gmail.com","instruments":"EURUSD,XAUUSD","timezone":"America/New_York"}' \
        --output .tmp/email_1.html

    python tools/render_email.py --clear-day --user-json '...' --output .tmp/email_1.html

Exit codes:
    0 — success
    1 — missing arguments or unreadable files
"""

import argparse
import json
import sys
from datetime import datetime, timezone, date as date_type
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS, CURRENCY_TO_INSTRUMENTS, TIMEZONE_ALIASES


# ── Time helpers ──────────────────────────────────────────────────────────────

def resolve_tz(tz_str: str) -> pytz.BaseTzInfo:
    """Accept alias (ET, IST …) or full IANA name. Returns pytz timezone."""
    upper = tz_str.strip().upper()
    iana = TIMEZONE_ALIASES.get(upper, tz_str.strip())
    try:
        return pytz.timezone(iana)
    except pytz.UnknownTimeZoneError:
        return pytz.UTC


def convert_utc_time(time_utc_str: str, user_tz: pytz.BaseTzInfo) -> str:
    """
    Convert a 'HH:MM' UTC string to the user's local time.
    Returns formatted string like '08:30 ET' or '14:00 IST'.
    """
    if not time_utc_str or time_utc_str == "TBD":
        return "TBD"
    try:
        today = date_type.today()
        parts = time_utc_str.strip().split(":")
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        utc_dt = datetime(today.year, today.month, today.day, hour, minute,
                          tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(user_tz)
        return local_dt.strftime("%H:%M")
    except Exception:
        return time_utc_str


def tz_display_name(user_tz: pytz.BaseTzInfo) -> str:
    """Return a short display name for the timezone, e.g. 'EST', 'IST'."""
    try:
        now = datetime.now(user_tz)
        return now.strftime("%Z")
    except Exception:
        return str(user_tz)


# ── Event filtering ───────────────────────────────────────────────────────────

def filter_events_for_user(analyses: list[dict], user_instruments: list[str]) -> list[dict]:
    """Return only events that affect at least one of the user's instruments."""
    relevant = []
    user_set = set(user_instruments)
    for item in analyses:
        analysis = item.get("analysis") or {}
        affected = set(analysis.get("affected_instruments") or [])
        if not affected:
            country = item.get("country", "").upper()
            affected = set(CURRENCY_TO_INSTRUMENTS.get(country, []))
        if affected & user_set:
            if analysis is not None and not analysis.get("affected_instruments"):
                analysis["affected_instruments"] = sorted(affected & user_set)
            relevant.append(item)
    return relevant


# ── HTML template ─────────────────────────────────────────────────────────────

EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forex Morning Alert</title>
<style>
  body{margin:0;padding:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;color:#1a1a2e}
  .wrap{max-width:660px;margin:0 auto;background:#ffffff}

  /* Header */
  .header{background:#1a2130;padding:24px 28px;border-radius:8px 8px 0 0}
  .header h1{margin:0;color:#ffffff;font-size:22px;font-weight:700}
  .header .sub{margin:6px 0 0;color:#d9a621;font-size:13px}
  .header .date{margin:4px 0 0;color:#94a3b8;font-size:12px}

  /* Intro */
  .intro{background:#f7fafc;padding:14px 28px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#4a5568}

  /* ── Quick Scan (priority preview) ── */
  .qs-wrap{padding:20px 28px;background:#fffdf5;border-bottom:3px solid #d9a621}
  .qs-title{font-size:13px;font-weight:700;color:#1a2130;letter-spacing:.5px;
            text-transform:uppercase;margin:0 0 12px;display:flex;align-items:center;gap:6px}
  .qs-table{width:100%;border-collapse:collapse;font-size:12px}
  .qs-table th{background:#1a2130;color:#d9a621;text-align:left;padding:7px 8px;
               font-size:10px;letter-spacing:.5px;text-transform:uppercase;font-weight:700}
  .qs-table td{padding:8px 8px;border-bottom:1px solid #f0f4f8;vertical-align:top;color:#2d3748}
  .qs-table tr:last-child td{border-bottom:none}
  .qs-table tr:hover td{background:#fffbeb}
  .qs-time{font-weight:700;color:#1a2130;white-space:nowrap}
  .qs-utc{display:block;color:#94a3b8;font-size:10px}
  .qs-event{font-weight:600;color:#1a2130}
  .qs-ccy{display:inline-block;background:#1a2130;color:#fff;font-size:9px;font-weight:700;
          padding:2px 6px;border-radius:10px;white-space:nowrap}
  .qs-nums{white-space:nowrap;color:#4a5568}
  .qs-note{color:#4a5568;font-size:11px;line-height:1.4;font-style:italic}
  .qs-no-events{color:#4a5568;font-size:12px;font-style:italic;padding:8px 0}

  /* Event detail cards */
  .event-card{padding:24px 28px;border-bottom:2px solid #f0f4f8}
  .event-badge{display:inline-block;background:#ef5350;color:#fff;font-size:10px;font-weight:700;
               padding:2px 8px;border-radius:12px;letter-spacing:.6px;margin-bottom:8px}
  .event-title{font-size:18px;font-weight:700;color:#1a2130;margin:0 0 4px}
  .event-meta{font-size:12px;color:#94a3b8;margin-bottom:16px}
  .numbers{display:flex;gap:0;margin-bottom:16px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden}
  .num-cell{flex:1;text-align:center;padding:10px 6px;background:#f7fafc}
  .num-cell+.num-cell{border-left:1px solid #e2e8f0}
  .num-label{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.5px;display:block}
  .num-value{font-size:16px;font-weight:700;color:#1a2130;display:block;margin-top:4px}
  .section-label{font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.6px;
                  margin:14px 0 4px;text-transform:uppercase}
  .section-body{font-size:13px;color:#2d3748;line-height:1.6;margin:0 0 10px}
  .instruments{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}
  .chip{background:#e8f4fd;color:#1a6bb5;font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px}
  .scenario{border-radius:6px;padding:12px 14px;margin:6px 0;font-size:13px;line-height:1.5}
  .beat{background:#e8faf7;border-left:4px solid #26a69a;color:#1a3a38}
  .miss{background:#fef2f1;border-left:4px solid #ef5350;color:#3a1a1a}
  .scenario strong{display:block;margin-bottom:4px;font-size:11px;letter-spacing:.5px}
  .note{font-size:12px;color:#4a5568;font-style:italic;margin-top:10px;padding:8px 12px;
        background:#fffbeb;border-left:3px solid #d9a621;border-radius:0 4px 4px 0}

  /* Clear / no-match */
  .clear-day{text-align:center;padding:40px 28px;color:#4a5568}
  .clear-day .icon{font-size:40px;margin-bottom:12px}
  .clear-day h2{color:#26a69a;margin:0 0 8px}
  .clear-day p{font-size:13px;line-height:1.6;margin:0}
  .no-match{padding:24px 28px;text-align:center;color:#4a5568;font-size:13px}

  /* Footer */
  .footer{background:#f7fafc;padding:16px 28px;text-align:center;
          font-size:11px;color:#94a3b8;border-radius:0 0 8px 8px;border-top:1px solid #e2e8f0}
  .footer a{color:#94a3b8}
</style>
</head>
<body>
<div class="wrap">

<!-- HEADER -->
<div class="header">
  <h1>Forex Morning Alert</h1>
  <div class="sub">{{ subtitle }}</div>
  <div class="date">{{ date_display }} &nbsp;·&nbsp; 06:30 UTC</div>
</div>

<!-- INTRO -->
<div class="intro">
  Good morning{% if user_name %}, <strong>{{ user_name }}</strong>{% endif %}.
  {% if clear_day %}
    Today's calendar is clear — no high-impact events scheduled.
  {% elif no_match %}
    Today has high-impact events, but none affect your instruments directly.
  {% else %}
    Here are today's high-impact events relevant to your instruments
    (<strong>{{ user_instruments }}</strong>).
    Times shown in <strong>{{ tz_display }}</strong>.
  {% endif %}
</div>

{% if clear_day %}
<!-- CLEAR DAY -->
<div class="clear-day">
  <div class="icon">✅</div>
  <h2>Clear Day — No Red-Folder Events</h2>
  <p>No high-impact economic events are scheduled today.<br>
     Markets should trade on technical factors and overnight sentiment.</p>
</div>

{% else %}

<!-- ─── QUICK SCAN — priority preview ─────────────────────────────────────── -->
<div class="qs-wrap">
  <div class="qs-title">📁 Quick Scan — All High-Impact Events Today</div>
  {% if all_events %}
  <table class="qs-table">
    <thead>
      <tr>
        <th>Time ({{ tz_display }})</th>
        <th>Event</th>
        <th>Ccy</th>
        <th>Prev → Fcst</th>
        <th>Key Takeaway</th>
      </tr>
    </thead>
    <tbody>
      {% for item in all_events %}
      {% set a = item.analysis or {} %}
      <tr>
        <td>
          <span class="qs-time">{{ item.local_time }}</span>
          <span class="qs-utc">{{ item.time_utc or item.time or 'TBD' }} UTC</span>
        </td>
        <td><span class="qs-event">{{ a.event_name or item.title }}</span></td>
        <td><span class="qs-ccy">{{ item.country }}</span></td>
        <td class="qs-nums">
          {{ item.previous or '—' }}&nbsp;→&nbsp;{{ item.forecast or '—' }}
        </td>
        <td class="qs-note">{{ a.trading_note or '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="qs-no-events">No high-impact events found for today.</div>
  {% endif %}
</div>

{% if no_match %}
<!-- NO MATCHING INSTRUMENTS -->
<div class="no-match">
  <p>⚪ Today's red-folder events do not directly affect your instruments
     (<strong>{{ user_instruments }}</strong>).<br>
     See the Quick Scan above for the full event list.</p>
</div>

{% else %}
<!-- ─── EVENT DETAIL CARDS ─────────────────────────────────────────────────── -->
{% for item in events %}
{% set a = item.analysis or {} %}
<div class="event-card">
  <span class="event-badge">🔴 HIGH IMPACT</span>
  <div class="event-title">{{ a.event_name or item.title }}</div>
  <div class="event-meta">
    {{ item.local_time }} {{ tz_display }}
    &nbsp;({{ item.time_utc or item.time or 'TBD' }} UTC)
    &nbsp;·&nbsp; {{ item.country }}
  </div>

  <!-- Numbers -->
  <div class="numbers">
    <div class="num-cell">
      <span class="num-label">PREVIOUS</span>
      <span class="num-value">{{ item.previous or '—' }}</span>
    </div>
    <div class="num-cell">
      <span class="num-label">FORECAST</span>
      <span class="num-value">{{ item.forecast or '—' }}</span>
    </div>
    <div class="num-cell">
      <span class="num-label">ACTUAL</span>
      <span class="num-value">{{ item.actual or '—' }}</span>
    </div>
  </div>

  <!-- Affected instruments -->
  {% if a.affected_instruments %}
  <div class="section-label">Your instruments affected</div>
  <div class="instruments">
    {% for inst in a.affected_instruments %}
    {% if inst in user_instrument_list %}
    <span class="chip">{{ inst }}</span>
    {% endif %}
    {% endfor %}
  </div>
  {% endif %}

  {% if a.plain_explanation %}
  <div class="section-label">What is this?</div>
  <p class="section-body">{{ a.plain_explanation }}</p>
  {% endif %}

  {% if a.historical_context %}
  <div class="section-label">Historical Context</div>
  <p class="section-body">{{ a.historical_context }}</p>
  {% endif %}

  {% if a.forecast_vs_previous %}
  <div class="section-label">Forecast vs Previous</div>
  <p class="section-body">{{ a.forecast_vs_previous }}</p>
  {% endif %}

  {% if a.bullish_scenario %}
  <div class="scenario beat">
    <strong>▲ BEAT SCENARIO</strong>
    {{ a.bullish_scenario }}
  </div>
  {% endif %}
  {% if a.bearish_scenario %}
  <div class="scenario miss">
    <strong>▼ MISS SCENARIO</strong>
    {{ a.bearish_scenario }}
  </div>
  {% endif %}

  {% if a.trading_note %}
  <div class="note">💡 {{ a.trading_note }}</div>
  {% endif %}
</div>
{% endfor %}
{% endif %}
{% endif %}

<!-- FOOTER -->
<div class="footer">
  Forex Morning Alert &nbsp;·&nbsp; Powered by OpenAI gpt-4o &nbsp;·&nbsp; Data: Forex Factory<br>
  Reply to this email to unsubscribe.
</div>

</div>
</body>
</html>"""


# ── Render logic ──────────────────────────────────────────────────────────────

def enrich_with_local_time(events: list[dict], user_tz: pytz.BaseTzInfo) -> list[dict]:
    """Add a `local_time` key to each event dict (converted from time_utc)."""
    for item in events:
        raw = item.get("time_utc") or item.get("time") or "TBD"
        item["local_time"] = convert_utc_time(raw, user_tz)
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Render personalised HTML email for one user.")
    parser.add_argument("--analyses",  default=PATHS["analyses"], help="Analyses JSON path")
    parser.add_argument("--user-json", required=True, help="JSON string of user record")
    parser.add_argument("--output",    required=True, help="Output HTML file path")
    parser.add_argument("--clear-day", action="store_true", help="Render the clear-day version")
    args = parser.parse_args()

    try:
        user = json.loads(args.user_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid --user-json: {exc}"}), file=sys.stderr)
        sys.exit(1)

    user_name            = user.get("name", "")
    user_instruments_str = user.get("instruments", "")
    user_instrument_list = [i.strip().upper() for i in user_instruments_str.split(",") if i.strip()]
    user_tz_str          = user.get("timezone", "UTC")
    user_tz              = resolve_tz(user_tz_str)
    tz_abbr              = tz_display_name(user_tz)

    from jinja2 import Environment, BaseLoader
    env      = Environment(loader=BaseLoader())
    template = env.from_string(EMAIL_TEMPLATE)

    date_display = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    if args.clear_day:
        html = template.render(
            clear_day=True, no_match=False,
            events=[], all_events=[],
            user_name=user_name,
            user_instruments=", ".join(user_instrument_list),
            user_instrument_list=user_instrument_list,
            subtitle="Clear Day — No High-Impact Events",
            date_display=date_display,
            tz_display=tz_abbr,
        )
    else:
        analyses_path = Path(args.analyses)
        if not analyses_path.exists():
            print(json.dumps({"error": f"Analyses file not found: {args.analyses}"}),
                  file=sys.stderr)
            sys.exit(1)

        payload       = json.loads(analyses_path.read_text(encoding="utf-8"))
        all_analyses  = payload.get("analyses", [])

        # All events (for Quick Scan, regardless of user instruments)
        all_events = enrich_with_local_time(list(all_analyses), user_tz)

        # Events filtered to user's instruments (for detail cards)
        relevant  = filter_events_for_user(list(all_analyses), user_instrument_list)
        relevant  = enrich_with_local_time(relevant, user_tz)
        no_match  = len(relevant) == 0

        event_count = len(relevant)
        subtitle = (
            f"{event_count} Event{'s' if event_count != 1 else ''} Affecting Your Instruments"
            if not no_match else "Events Today — None Match Your Instruments"
        )

        html = template.render(
            clear_day=False,
            no_match=no_match,
            events=relevant,
            all_events=all_events,
            user_name=user_name,
            user_instruments=", ".join(user_instrument_list),
            user_instrument_list=user_instrument_list,
            subtitle=subtitle,
            date_display=date_display,
            tz_display=tz_abbr,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(json.dumps({
        "status":    "ok",
        "output":    args.output,
        "user":      user.get("email"),
        "clear_day": args.clear_day,
        "timezone":  tz_abbr,
    }, indent=2))


if __name__ == "__main__":
    main()
