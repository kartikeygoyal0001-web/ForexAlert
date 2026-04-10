# Add User Workflow

## Objective
Subscribe a new user to the Forex Factory morning alert (stored in Supabase).

## Prerequisites
- Supabase project created and `SUPABASE_URL` / `SUPABASE_KEY` set in `.env`
- `users` table exists in Supabase (run the SQL below once if it doesn't)

## One-Time Supabase Table Setup

Run this SQL in your Supabase project → **SQL Editor**:

```sql
CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    instruments  TEXT NOT NULL,
    timezone     TEXT NOT NULL DEFAULT 'UTC',
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes        TEXT
);
```

## Required Inputs
- Subscriber's full name
- Email address
- Instruments they trade (comma-separated)
- **Trading timezone** — required. Use a short code or full IANA name:

| Short code | Timezone        | Region            |
|------------|-----------------|-------------------|
| `ET`       | America/New_York | US East (NY/Boston) |
| `CT`       | America/Chicago  | US Central        |
| `MT`       | America/Denver   | US Mountain       |
| `PT`       | America/Los_Angeles | US West        |
| `GMT`/`UTC`| UTC             | London (winter)   |
| `BST`      | Europe/London   | London (summer)   |
| `CET`      | Europe/Paris    | Central Europe    |
| `IST`      | Asia/Kolkata    | India             |
| `SGT`      | Asia/Singapore  | Singapore         |
| `JST`      | Asia/Tokyo      | Japan             |
| `HKT`      | Asia/Hong_Kong  | Hong Kong         |
| `AEST`     | Australia/Sydney | Australia         |
| `MSK`      | Europe/Moscow   | Russia            |
| `GST`      | Asia/Dubai      | UAE / Gulf        |
| `PKT`      | Asia/Karachi    | Pakistan          |

Full IANA names (e.g. `America/New_York`) are also accepted.

## Valid Instruments
Common instruments: `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `USDCAD`, `AUDUSD`, `NZDUSD`,
`XAUUSD`, `XAGUSD`, `EURGBP`, `EURJPY`, `GBPJPY`, `AUDJPY`, `US30`, `NAS100`, `SPX500`

Validate first:
```bash
python tools/manage_users.py --validate-instruments "EURUSD,XAUUSD"
```

## Steps

**1. Add the subscriber:**
```bash
python tools/manage_users.py --add \
    --name "Alice Rahman" \
    --email "alice@gmail.com" \
    --instruments "EURUSD,XAUUSD,GBPUSD" \
    --timezone ET
```
`--timezone` is required. The timezone controls what time events appear in the email Quick Scan.

**2. Confirm they appear in the list:**
```bash
python tools/manage_users.py --list
```

**3. Optional — send a test email immediately:**
```bash
python tools/send_all_emails.py
```

## Updating Instruments
```bash
python tools/manage_users.py --update \
    --email "alice@gmail.com" \
    --instruments "EURUSD,USDJPY,XAUUSD"
```

## Updating Timezone
```bash
python tools/manage_users.py --update-tz \
    --email "alice@gmail.com" \
    --timezone IST
```

## Deactivating
```bash
python tools/manage_users.py --deactivate --email "alice@gmail.com"
```
Soft-delete — record is kept, just excluded from sends.

## Re-activating
```bash
python tools/manage_users.py --activate --email "alice@gmail.com"
```
