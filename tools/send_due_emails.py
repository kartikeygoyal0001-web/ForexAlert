#!/usr/bin/env python3
"""
send_due_emails.py — WAT Framework Tool
Sends alert emails to subscribers whose alert_time falls within the current
30-minute window (in each user's own timezone).

Run every 30 minutes by Windows Task Scheduler.

Usage:
    python tools/send_due_emails.py
    python tools/send_due_emails.py --dry-run   (print who would be emailed, don't send)
    python tools/send_due_emails.py --window 60  (use a 60-minute window instead of 30)

Exit codes:
    0 — success (even if no users were due, or some sends failed — check log)
    1 — analyses.json not found (pipeline hasn't run today yet)
    2 — fatal error
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

ROOT  = Path(__file__).parent.parent
TOOLS = Path(__file__).parent

sys.path.insert(0, str(ROOT))
from config import PATHS

RENDER_TOOL = TOOLS / "render_email.py"
SEND_TOOL   = TOOLS / "send_gmail.py"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_supabase():
    try:
        from supabase import create_client
    except ImportError:
        print("[send-due] supabase not installed", file=sys.stderr)
        sys.exit(2)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        print("[send-due] SUPABASE_URL / SUPABASE_KEY missing", file=sys.stderr)
        sys.exit(2)
    from supabase import create_client
    return create_client(url, key)


def get_active_users() -> list[dict]:
    sb = get_supabase()
    try:
        result = sb.table("users").select("*").eq("active", True).order("id").execute()
        return result.data or []
    except Exception as exc:
        print(f"[send-due] Supabase query failed: {exc}", file=sys.stderr)
        sys.exit(2)


def is_user_due(user: dict, now_utc: datetime, window_minutes: int) -> bool:
    """Return True if the user's alert_time falls within the next `window_minutes` from now."""
    alert_str = user.get("alert_time", "")
    tz_name   = user.get("timezone", "UTC")

    if not alert_str:
        return False

    # Parse HH:MM
    try:
        h, m = map(int, alert_str.split(":"))
    except ValueError:
        return False

    # Convert now to user's timezone
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    now_local = now_utc.astimezone(tz)

    # Build today's alert datetime in user's timezone
    alert_local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)

    # How many minutes past or before the alert time are we?
    diff_seconds = (now_local - alert_local).total_seconds()
    # Due if we're within [0, window_minutes) minutes AFTER the scheduled time
    return 0 <= diff_seconds < window_minutes * 60


def build_subject(payload: dict) -> str:
    if payload.get("clear_day"):
        return f"Forex Alert: Clear Day — No Red Events {payload.get('date', '')}"
    n = payload.get("event_count", 0)
    return f"Forex Alert: {n} High-Impact Event{'s' if n != 1 else ''} Today — {payload.get('date', '')}"


def send_for_user(user: dict, payload: dict, clear_day: bool) -> dict:
    uid        = user["id"]
    email      = user["email"]
    email_file = Path(PATHS["email"].format(user_id=uid))

    render_args = [
        sys.executable, str(RENDER_TOOL),
        "--user-json", json.dumps(user),
        "--output",    str(email_file),
    ]
    if clear_day:
        render_args.append("--clear-day")
    else:
        render_args += ["--analyses", PATHS["analyses"]]

    render_result = subprocess.run(render_args, capture_output=True, text=True)
    if render_result.returncode != 0:
        return {
            "user_id": uid, "email": email, "status": "failed",
            "stage": "render", "error": render_result.stderr.strip()[:300],
        }

    send_clear = os.getenv("SEND_CLEAR_DAY_EMAIL", "true").lower() == "true"
    if clear_day and not send_clear:
        email_file.unlink(missing_ok=True)
        return {"user_id": uid, "email": email, "status": "skipped", "reason": "clear_day"}

    subject = build_subject(payload)
    send_args = [
        sys.executable, str(SEND_TOOL),
        "--to",        email,
        "--subject",   subject,
        "--html-file", str(email_file),
    ]

    send_result = subprocess.run(send_args, capture_output=True, text=True)
    email_file.unlink(missing_ok=True)

    if send_result.returncode != 0:
        return {
            "user_id": uid, "email": email, "status": "failed",
            "stage": "send", "error": send_result.stderr.strip()[:300],
        }

    try:
        send_data = json.loads(send_result.stdout)
        return {"user_id": uid, "email": email, "status": "sent",
                "message_id": send_data.get("message_id")}
    except json.JSONDecodeError:
        return {"user_id": uid, "email": email, "status": "sent", "message_id": None}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Send alerts to users whose time window is now.")
    parser.add_argument("--dry-run", action="store_true", help="Print who would be emailed, don't send")
    parser.add_argument("--window", type=int, default=30, help="Match window in minutes (default: 30)")
    args = parser.parse_args()

    analyses_path = Path(PATHS["analyses"])
    if not analyses_path.exists():
        print("[send-due] analyses.json not found — pipeline hasn't run today yet. Exiting.", flush=True)
        sys.exit(0)  # Not an error — just too early

    payload   = json.loads(analyses_path.read_text(encoding="utf-8"))
    clear_day = payload.get("clear_day", False)
    now_utc   = datetime.now(timezone.utc)

    print(f"[send-due] {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} | window={args.window}min | "
          f"clear_day={clear_day}", flush=True)

    users = get_active_users()
    if not users:
        print("[send-due] No active subscribers.", flush=True)
        sys.exit(0)

    due_users = [u for u in users if is_user_due(u, now_utc, args.window)]

    print(f"[send-due] {len(due_users)}/{len(users)} user(s) due now.", flush=True)
    if not due_users:
        sys.exit(0)

    sent = failed = skipped = 0
    log_entries = []

    for user in due_users:
        tz   = user.get("timezone", "UTC")
        atime = user.get("alert_time", "?")
        print(f"[send-due] -> {user['email']} | alert={atime} | tz={tz}", flush=True)

        if args.dry_run:
            print(f"[send-due]    DRY RUN — skipping send", flush=True)
            log_entries.append({"user_id": user["id"], "email": user["email"],
                                "status": "dry_run"})
            continue

        entry = send_for_user(user, payload, clear_day)
        log_entries.append(entry)

        if entry["status"] == "sent":
            sent += 1
            print(f"[send-due]    SENT (id={entry.get('message_id', '?')})", flush=True)
        elif entry["status"] == "skipped":
            skipped += 1
            print(f"[send-due]    SKIPPED ({entry.get('reason')})", flush=True)
        else:
            failed += 1
            print(f"[send-due]    FAILED @ {entry.get('stage')}: {entry.get('error','')[:100]}",
                  file=sys.stderr)

    # Append to today's send log
    date_str  = payload.get("date", now_utc.strftime("%Y-%m-%d"))
    log_path  = Path(PATHS["run_log"].format(date=date_str))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing_entries = existing.get("entries", [])
    existing_sent    = existing.get("sent", 0)
    existing_failed  = existing.get("failed", 0)
    existing_skipped = existing.get("skipped", 0)

    merged = {
        "date":        date_str,
        "clear_day":   clear_day,
        "users_total": len(users),
        "sent":        existing_sent    + sent,
        "failed":      existing_failed  + failed,
        "skipped":     existing_skipped + skipped,
        "entries":     existing_entries + log_entries,
        "last_run_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    log_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    print(f"[send-due] Done. sent={sent} failed={failed} skipped={skipped}", flush=True)


if __name__ == "__main__":
    main()
