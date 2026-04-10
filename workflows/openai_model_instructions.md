# OpenAI Model Instructions — Forex Morning Alert System

This document explains exactly what we ask the OpenAI model to do, why we ask it that way,
and how to adjust the instructions if the output quality needs improvement.

The instructions live in `tools/generate_event_analysis.py` as `SYSTEM_PROMPT` and `build_user_prompt()`.

---

## What the Model Does

For each high-impact economic event on Forex Factory, the model receives:

1. **Structured event data** — title, currency, scheduled time (UTC), forecast, previous, actual
2. **A list of instruments** — the forex pairs and commodities affected by that currency
3. **Live news context** *(optional, if Tavily or Firecrawl retrieved results)* — analyst previews, market expectations, and commentary from FXStreet, Reuters, ForexLive, and DailyFX

The model returns a structured JSON object with 8 fields. This JSON is then:
- Embedded into the PDF report (cover, per-event sections, scenario boxes)
- Rendered into the subscriber HTML email (event cards)
- Used to filter which events are shown to each subscriber (based on `affected_instruments`)

**The model's output is parsed by code — not read by a human.** Invalid JSON breaks the pipeline. This is why the prompts are strict about format.

---

## Full System Prompt Explanation

```
You are the analysis engine for an automated Forex Factory Morning Alert system.
```
**Why:** Setting the role as "analysis engine" (not "helpful assistant") removes conversational
fluff and reinforces that the output is machine-consumed. The model should produce structured
output, not prose explanations.

---

```
You are part of a fully automated pipeline — your output is parsed by code.
This means you must return ONLY valid JSON. Never include markdown, code blocks,
explanatory text, or any content outside the JSON object.
```
**Why:** Without this, gpt-4o sometimes wraps its response in ```json ... ``` markdown fences,
adds an explanation before the JSON ("Here is the analysis:"), or appends a summary after.
All of these break `json.loads()`. The instruction is explicit and repeated.

---

```
Retail forex traders who:
- Trade instruments like EURUSD, XAUUSD, GBPUSD
- Have 1-3 years of experience
- Need plain-English explanations, not academic language
- Check this briefing at 06:30 UTC before the trading session opens
```
**Why:** The model adjusts its vocabulary and depth based on the described audience. Without this,
it tends to write like a Bloomberg terminal or an academic paper. Retail traders don't know what
"non-seasonally adjusted PCE deflator rebasing" means — they need to know whether USD goes up or down.

---

## What Each JSON Field Should Contain

### `event_name`
Short plain-English label. We often shorten the FF title.
- Good: `"US Core CPI m/m"` or `"Canada Employment Change"`
- Bad: `"Consumer Price Index (ex Food & Energy) Month-on-Month"`

### `plain_explanation`
2-3 sentences answering: *What does this indicator measure? Why does the market care?*
- Must be written for a trader, not an economist
- Should mention: what the number measures, what central bank watches it, what direction is "strong"
- Example:
  > "Core CPI measures the monthly change in consumer prices excluding food and energy.
  > The Fed watches this closely — if it runs too hot, they raise rates (bullish USD);
  > if it cools, rate-cut expectations grow (bearish USD). It's the most market-moving
  > inflation gauge on the US calendar."

### `historical_context`
Grounds the analysis in recent data. Uses the `previous` value from the event.
- If news context is provided: synthesize what analysts are saying about the trend
- If not: use training-data knowledge of the indicator's recent history
- Example:
  > "March CPI came in at 0.2%, below the 0.3% forecast — the second consecutive miss.
  > Inflation is clearly decelerating from the 2024 highs, reinforcing Fed dovish pivot expectations."

### `forecast_vs_previous`
Compares the forecast to the previous release and explains what that means.
- Always state: higher/lower/in-line
- Always explain what that direction means for rate expectations
- Example:
  > "The forecast of 0.3% is slightly above February's 0.2%, suggesting analysts expect
  > mild re-acceleration. A beat would reinforce hawkish Fed positioning and support USD."

### `affected_instruments`
List of instrument strings from the provided list. Most directly impacted pairs only.
- USD event: EURUSD, GBPUSD, USDJPY, XAUUSD are typical
- Don't include pairs with no meaningful USD exposure (e.g. EURGBP for a USD event)
- Typical count: 3-6 instruments

### `bullish_scenario`
What happens if the data **beats** forecast. Written from the event currency's perspective.
- "Bullish" = bullish for the event currency
- Name specific pairs and their direction
- Include a key price level if known
- Example:
  > "USD strengthens — EURUSD tests 1.0800 support, XAUUSD sells off below $2,300 as
  > rate-hike expectations revive. GBPUSD likely follows EURUSD lower."

### `bearish_scenario`
What happens if the data **misses** forecast.
- Example:
  > "USD weakens — EURUSD reclaims 1.0950 resistance, XAUUSD spikes toward $2,380 as
  > the rate-cut narrative strengthens. Risk-on tone may lift AUDUSD and NZDUSD as well."

### `trading_note`
One concrete, time-specific, actionable sentence.
- Focus on: entry timing, key level, or risk management
- Bad: "Be careful around this release as it can cause volatility."
- Good: "Watch the 13:30 UTC candle — wait for the first 5-minute bar to close before
  committing to a direction, as the initial spike often reverses."

---

## How News Context Changes the Output

When Tavily or Firecrawl retrieves live analyst commentary, it's injected into the user
prompt before the event data, labelled clearly:

```
## Live Market Context (from tavily — fetched today)
Market consensus summary: [Tavily's AI-synthesized answer]

[FXStreet article] Analysts expect Core CPI to re-accelerate to 0.3%...
[Reuters] Fed officials have signaled patience ahead of today's data...
```

The model is instructed to use this context to:
1. Ground `historical_context` in what analysts are actually saying today
2. Reference specific analyst themes (e.g. "shelter costs are the upside risk")
3. Incorporate market positioning if mentioned (e.g. "market is priced for 0.3%")

**Quality difference with vs. without news context:**

| Field | Without news context | With news context |
|---|---|---|
| `historical_context` | Based on training data (may be stale) | Based on today's analyst commentary |
| `forecast_vs_previous` | Generic directional comparison | Includes analyst consensus and positioning |
| `bullish_scenario` | Model's training knowledge of levels | May include analyst-cited specific levels |
| `trading_note` | Generic timing advice | May reference specific technical setup analysts are watching |

---

## Model Configuration

In `generate_event_analysis.py`:

```python
model="gpt-4o"           # Best reasoning + structured JSON output
max_tokens=1000          # Enough for all 8 fields with detail
temperature=0.2          # Low = precise, repeatable output (not creative)
response_format={"type": "json_object"}  # Forces valid JSON output at API level
```

**Why temperature 0.2?**
Lower temperature means the model makes fewer "creative" choices. For structured analysis
that needs to be consistent and accurate, we want low variance. Higher temperature (0.7+)
produces more varied prose but risks the model inventing price levels or fabricating data.

**Why gpt-4o and not gpt-4o-mini?**
This is the core value-add of the system. The analysis quality is what justifies the daily email.
gpt-4o's reasoning is noticeably better at:
- Understanding complex macroeconomic relationships
- Accurately naming affected instruments
- Writing scenario descriptions that are specific and correct (not generic)
At ~$0.01 per event analysis and 3-8 events per day, the cost is negligible.

---

## Retry and Fallback Chain

1. **Normal call** → parse JSON → if valid, use it
2. **JSON parse failure** → retry with strict instruction ("Start with { and end with }")
3. **Second parse failure** OR **API error after retry** → use `build_raw_fallback()`:
   - `plain_explanation`: "Analysis unavailable — see forecast and previous values"
   - `affected_instruments`: first 5 instruments from CURRENCY_TO_INSTRUMENTS mapping
   - `bullish/bearish_scenario`: generic directional template using actual forecast/previous values

The fallback ensures the pipeline never aborts due to OpenAI issues — subscribers still
receive event data even if the AI analysis is missing.

---

## Prompt Tuning Guide

If you want to adjust what the model produces, edit these locations in `generate_event_analysis.py`:

| What to change | Where |
|---|---|
| Tone / expertise level of end user | `SYSTEM_PROMPT` → "Who the End Users Are" section |
| Output length per field | `ANALYSIS_SCHEMA` → description for each field |
| Field-specific quality instructions | `SYSTEM_PROMPT` → "Output Quality Standards" |
| How news context is used | `SYSTEM_PROMPT` → "If News Context Is Provided" |
| How the event data is presented | `build_user_prompt()` function |
| JSON schema structure | `ANALYSIS_SCHEMA` dict (also update PDF and email templates if keys change) |
| Model, temperature, max_tokens | `call_openai()` function |

**To add a new output field:**
1. Add the key + description to `ANALYSIS_SCHEMA` in `generate_event_analysis.py`
2. Add the field to `build_raw_fallback()` in the same file
3. Add the field to the HTML template in `render_email.py` (Jinja2 block)
4. Add the field to the PDF section builder in `generate_pdf_report.py`

---

## Cost Estimate

| Scenario | Events/day | Est. cost/day |
|---|---|---|
| Light day (1-2 events) | 2 | ~$0.02 |
| Normal day (3-5 events) | 4 | ~$0.04 |
| Heavy day (NFP + CPI + FOMC) | 8 | ~$0.08 |
| Monthly total | ~80 events | ~$0.80 |

Input tokens (~500 with news context) + output tokens (~300) ≈ 800 tokens per event.
At gpt-4o pricing of ~$5/1M input + $15/1M output, cost is negligible.

---

## News API Cost Estimate

| Service | Free tier | Daily usage | Monthly usage |
|---|---|---|---|
| Tavily | 1,000 searches/month | 3-8 searches | ~120 searches |
| Firecrawl | 500 credits/month | 3-8 scrapes | ~120 credits |

Both are well within free tier limits for daily use.
