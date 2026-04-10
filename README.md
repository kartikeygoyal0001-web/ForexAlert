# ForexAlert

> AI-powered daily Forex Factory event briefings delivered to your inbox before the market opens.

**Built by Kartikey Goyal**

---

## Overview

ForexAlert is a personalised email alert system that fetches high-impact economic events from Forex Factory, runs AI-powered analysis on each event, and delivers a tailored morning briefing to every subscriber at their individually chosen time — in their own timezone.

No bulk blast. No generic summary. Each subscriber gets their email exactly when they asked for it, filtered to the instruments they actually trade.

---

## Features

- **Automated Event Scraping** — Fetches high-impact red-folder events from Forex Factory every morning
- **AI-Powered Analysis** — Beat / miss scenarios, trading notes, and market context generated per event
- **Personalised Delivery** — Each subscriber receives their briefing at their own chosen time
- **Timezone-Aware** — Full global timezone support via Python `zoneinfo`
- **Instrument Filtering** — Users pick the pairs and instruments they trade; irrelevant events are filtered out
- **Self-Service Management** — Subscribers can update preferences or cancel at any time via `/manage`
- **Trader-Themed UI** — Dark, terminal-style signup and management pages

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | Flask 3.x (Python) |
| Database | Supabase (PostgreSQL) |
| Email Delivery | Gmail API (OAuth 2.0) |
| AI Analysis | OpenAI GPT-4o |
| News Enrichment | Tavily / Firecrawl |
| Scheduler | Windows Task Scheduler |
| Frontend | Vanilla HTML / CSS / JS |

---

## Project Structure

```
ForexAlert/
├── app.py                         # Flask web application (signup, manage, success)
├── config.py                      # Path constants and shared configuration
├── requirements.txt               # Python dependencies
├── run_alert.bat                  # Scheduler entry: daily pipeline (data + analysis)
├── run_send_due.bat               # Scheduler entry: per-user email send (every 30 min)
│
├── templates/                     # Jinja2 HTML templates
│   ├── index.html                 # Signup page with live chart loading animation
│   ├── manage.html                # Subscription management & preferences
│   └── success.html               # Post-signup confirmation
│
├── tools/                         # Pipeline scripts (WAT framework)
│   ├── run_morning_alert.py       # Master orchestrator — called by ForexPipeline task
│   ├── fetch_ff_events.py         # Scrape Forex Factory high-impact events
│   ├── filter_events_today.py     # Filter events by date and impact level
│   ├── fetch_event_news.py        # Enrich events with live news context (Tavily)
│   ├── generate_all_analyses.py   # Run AI analysis across all events
│   ├── generate_event_analysis.py # Per-event AI analysis (GPT-4o)
│   ├── generate_charts.py         # Price chart generation
│   ├── fetch_chart_data.py        # Fetch OHLCV data for chart rendering
│   ├── generate_pdf_report.py     # Optional PDF report generation
│   ├── render_email.py            # Build personalised HTML emails per user
│   ├── send_due_emails.py         # Send emails to users whose alert window is now
│   ├── send_all_emails.py         # Bulk send utility (manual use)
│   ├── send_gmail.py              # Gmail API send wrapper
│   └── manage_users.py            # CLI user management utility
│
└── workflows/                     # Agent SOPs (WAT framework)
    ├── morning_alert_pipeline.md  # Full pipeline walkthrough
    ├── add_user.md                # How to add / modify users
    ├── setup_scheduler.md         # Windows Task Scheduler setup guide
    └── openai_model_instructions.md
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/ForexAlert.git
cd ForexAlert
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
GMAIL_SENDER=your_gmail_address@gmail.com
ADMIN_EMAIL=your_admin_email@gmail.com
SEND_CLEAR_DAY_EMAIL=true
```

### 3. Gmail OAuth

Place `gmail_credentials.json` (downloaded from Google Cloud Console) in the project root. On first run, the OAuth flow will generate `token.json` automatically.

### 4. Run the web app

```bash
python app.py
```

Signup page → `http://localhost:5000`

### 5. Schedule automated tasks (Windows)

Open PowerShell and follow the instructions in `workflows/setup_scheduler.md` to register two tasks:

| Task | Script | Schedule |
|------|--------|----------|
| `ForexPipeline` | `run_alert.bat` | Daily at your chosen time (e.g. 11:00 AM) |
| `ForexSendDue` | `run_send_due.bat` | Every 30 minutes |

---

## How It Works

```
MORNING (once daily)                    EVERY 30 MINUTES
────────────────────────────────        ──────────────────────────────
run_morning_alert.py                    send_due_emails.py
  │                                       │
  ├─ fetch_ff_events.py                   ├─ load analyses.json
  ├─ filter_events_today.py               ├─ for each active user:
  ├─ fetch_event_news.py (enrichment)     │    check alert_time vs now_utc
  └─ generate_all_analyses.py             │    (per user's timezone)
       │                                  ├─ render_email.py  → HTML
       └─ .tmp/analyses.json             └─ send_gmail.py    → inbox
```

The pipeline runs once to produce `analyses.json`. The send task runs every 30 minutes and delivers to whichever subscribers have their chosen alert time falling in the current window — so a user who set 07:00 IST gets their email at 07:00 IST, not in a bulk blast with everyone else.

---

## Author

**Kartikey Goyal**

---

*Built with the WAT Framework — Workflows · Agents · Tools*
