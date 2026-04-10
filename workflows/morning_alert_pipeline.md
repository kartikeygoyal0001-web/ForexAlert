# Morning Alert Pipeline

## Objective
Run the full Forex Factory morning alert pipeline every weekday at 06:30 UTC.
Fetch high-impact events, enrich with live news context, generate AI analysis,
and email all subscribers a personalised HTML report.

## Trigger
Windows Task Scheduler → `python tools/run_morning_alert.py` → daily at 06:30 UTC.

## Required Inputs
- `.env` with `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `ADMIN_EMAIL`
  and optionally `TAVILY_API_KEY` / `FIRECRAWL_API_KEY`
- `gmail_credentials.json` and `token.json` at project root
- Supabase `users` table with at least one active subscriber (see `add_user.md`)

## Execution

```bash
# Full pipeline (normal use)
python tools/run_morning_alert.py

# Test run without sending emails
python tools/run_morning_alert.py --dry-run

# Force run on weekend (for testing)
python tools/run_morning_alert.py --dry-run --force-weekend

# Run individual steps manually (useful when debugging a specific stage)
python tools/fetch_ff_events.py
python tools/filter_events_today.py
python tools/fetch_event_news.py
python tools/generate_all_analyses.py
python tools/send_all_emails.py
```

## Step-by-Step

| Step | Script | Output | Skipped if | Fatal? |
|---|---|---|---|---|
| 1. Fetch | `fetch_ff_events.py` | `.tmp/ff_events_raw.json` | — | Yes |
| 2. Filter | `filter_events_today.py` | `.tmp/ff_events_today.json` | — | Yes |
| 3. News | `fetch_event_news.py` | `.tmp/event_news_context.json` | clear_day | No |
| 4. Analyze | `generate_all_analyses.py` | `.tmp/analyses.json` | clear_day | No |
| 5. Send | `send_all_emails.py` | `.tmp/run_log_DATE.json` | dry-run | No |

## What the Email Contains

Each subscriber receives a personalised HTML email with:

1. **⚡ Quick Scan table** (top of email) — ALL high-impact events for the day,
   with times shown in the subscriber's **trading timezone**, forecast vs previous,
   and a one-line key takeaway. Designed for busy traders who want the full picture
   at a glance without scrolling.

2. **Detailed event cards** — only events affecting the subscriber's instruments,
   with full AI analysis: plain explanation, historical context, beat/miss scenarios,
   and trading note.

Subscriber timezones are set at signup (`--timezone ET`, `--timezone IST`, etc.)
and can be updated any time with `--update-tz`.

## Step 3 Detail — News Enrichment (fetch_event_news.py)

**Data sources searched:**
- FXStreet (event previews, analyst expectations)
- ForexLive (real-time commentary)
- DailyFX (market analysis)
- Reuters (macro news)
- BabyPips (retail trader context)

**Provider strategy:**
1. Tavily API (primary) — structured, fast, purpose-built for AI agents
2. Firecrawl API (fallback) — deeper scraping if Tavily not configured
3. Empty context (graceful fallback) — analysis still runs without news

**Configuration:**
```bash
# .env
TAVILY_API_KEY=tvly-...    # Get at tavily.com (1000 free searches/month)
FIRECRAWL_API_KEY=fc-...   # Get at firecrawl.dev (500 free credits/month)
```

Both are optional — the pipeline continues without them.

## Expected Outputs
- Each subscriber receives an HTML email with a Quick Scan preview + per-instrument event cards
- Clear-day email: short "no events today" version with an empty Quick Scan
- Run log at `.tmp/run_log_YYYY-MM-DD.json`
- Pipeline log at `.tmp/pipeline_log_YYYY-MM-DD.json`

## Error Handling

| Condition | Behaviour |
|---|---|
| FF JSON endpoint down | JBlanked API fallback. Both down → admin alert + exit 1 |
| Zero high-impact events | `clear_day=true` → short email, skip news/analysis |
| Weekend (Sat/Sun) | Exit 0 silently — no emails |
| Tavily AND Firecrawl both unavailable | Skip news step — analysis runs without context |
| OpenAI 429 rate limit | Sleep 30s, retry once. If fails → raw fallback (no AI text) |
| OpenAI returns invalid JSON | Retry with strict prompt. If fails → raw data fallback |
| Gmail send fails for user | Log failure, continue to next user |
| Supabase unreachable | send_all_emails.py exits 2 — pipeline logs failure |

## .tmp File Reference

| File | Created by | Purpose |
|---|---|---|
| `ff_events_raw.json` | fetch_ff_events.py | Full week's FF events |
| `ff_events_today.json` | filter_events_today.py | Today's high-impact events only |
| `event_news_context.json` | fetch_event_news.py | Live analyst snippets per event |
| `analyses.json` | generate_all_analyses.py | OpenAI analysis for all events |
| `email_{user_id}.html` | send_all_emails.py | Per-user HTML (deleted after send) |
| `run_log_YYYY-MM-DD.json` | send_all_emails.py | Delivery status per user |
| `pipeline_log_YYYY-MM-DD.json` | run_morning_alert.py | Step-by-step pipeline status |

## Manual Re-run Steps
If the pipeline failed partway through, re-run from the failed step:
```bash
# Fetch + filter failed → check network, re-run from start
python tools/run_morning_alert.py --dry-run

# News step failed → safe to re-run standalone (no cost)
python tools/fetch_event_news.py

# Analysis failed → re-run (uses OpenAI credits)
python tools/generate_all_analyses.py

# Send failed → re-run send only (won't re-generate anything)
python tools/send_all_emails.py
```

## Lessons Learned
_Append findings here as the system runs._

- 2026-04-10: Initial deployment. Pipeline structure validated.
- 2026-04-10: FF JSON endpoint returns ISO 8601 datetimes (`2026-04-10T08:30:00-04:00`) — fixed in filter_events_today.py.
- 2026-04-10: When AI analysis is unavailable, instrument list falls back to CURRENCY_TO_INSTRUMENTS.
- 2026-04-10: News enrichment step added (Tavily + Firecrawl). Non-fatal.
- 2026-04-10: Migrated from SQLite to Supabase. PDF/chart steps removed. Quick Scan added to email.
