#!/usr/bin/env python3
"""
send_all_emails.py — WAT Framework Tool
Loops over all active subscribers (Supabase), renders a personalised HTML email
for each, and sends via Gmail API. Writes a run log on completion.

Usage:
    python tools/send_all_emails.py
    python tools/send_all_emails.py --analyses .tmp/analyses.json

Exit codes:
    0 — success (even if some individual sends failed — check run log)
    1 — no active users or missing required files
    2 — fatal error
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PATHS

RENDER_TOOL = Path(__file__).parent / "render_email.py"
SEND_TOOL   = Path(__file__).parent / "send_gmail.py"


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_active_users() -> list[dict]:
    try:
        from supabase import create_client
    except ImportError:
        print("[send-all] supabase package not installed — run: pip install supabase", file=sys.stderr)
        sys.exit(2)

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        print("[send-all] SUPABASE_URL and SUPABASE_KEY must be set in .env", file=sys.stderr)
        sys.exit(2)

    sb = create_client(url, key)
    try:
        result = sb.table("users").select("*").eq("active", True).order("id").execute()
        return result.data or []
    except Exception as exc:
        print(f"[send-all] Supabase query failed: {exc}", file=sys.stderr)
        sys.exit(2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_subject(payload: dict) -> str:
    if payload.get("clear_day"):
        date_str = payload.get("date", "")
        return f"Forex Alert: Clear Day — No Red Events {date_str}"
    n = payload.get("event_count", 0)
    date_str = payload.get("date", "")
    return f"Forex Alert: {n} High-Impact Event{'s' if n != 1 else ''} Today — {date_str}"


def send_for_user(user: dict, payload: dict, clear_day: bool) -> dict:
    """Render and send one user's email. Returns a log entry dict."""
    uid   = user["id"]
    email = user["email"]
    email_file = Path(PATHS["email"].format(user_id=uid))

    # ── Step 1: Render ────────────────────────────────────────────────────────
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

    # ── Step 2: Gate on env flags ─────────────────────────────────────────────
    send_clear = os.getenv("SEND_CLEAR_DAY_EMAIL", "true").lower() == "true"
    if clear_day and not send_clear:
        return {"user_id": uid, "email": email, "status": "skipped", "reason": "clear_day"}

    # ── Step 3: Send HTML email (no attachment) ───────────────────────────────
    subject = build_subject(payload)
    send_args = [
        sys.executable, str(SEND_TOOL),
        "--to",        email,
        "--subject",   subject,
        "--html-file", str(email_file),
    ]

    send_result = subprocess.run(send_args, capture_output=True, text=True)
    if send_result.returncode != 0:
        return {
            "user_id": uid, "email": email, "status": "failed",
            "stage": "send", "error": send_result.stderr.strip()[:300],
        }

    try:
        send_data = json.loads(send_result.stdout)
        return {
            "user_id":    uid,
            "email":      email,
            "status":     "sent",
            "message_id": send_data.get("message_id"),
        }
    except json.JSONDecodeError:
        return {"user_id": uid, "email": email, "status": "sent", "message_id": None}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Send morning alert emails to all active subscribers.")
    parser.add_argument("--analyses", default=PATHS["analyses"], help="Analyses JSON path")
    args = parser.parse_args()

    users = get_active_users()
    if not users:
        print(json.dumps({"error": "No active subscribers found"}), file=sys.stderr)
        sys.exit(1)

    analyses_path = Path(args.analyses)
    if analyses_path.exists():
        payload = json.loads(analyses_path.read_text(encoding="utf-8"))
    else:
        payload = {"clear_day": False, "event_count": 0, "date": ""}

    clear_day = payload.get("clear_day", False)

    print(f"[send-all] Sending to {len(users)} subscriber(s) | clear_day={clear_day}", flush=True)

    log_entries = []
    sent = failed = skipped = 0

    for user in users:
        print(f"[send-all] -> {user['email']} ({user.get('instruments','')}) tz={user.get('timezone','UTC')}",
              flush=True)
        entry = send_for_user(user, payload, clear_day)
        log_entries.append(entry)

        if entry["status"] == "sent":
            sent += 1
            print(f"[send-all]    SENT (id={entry.get('message_id', '?')})", flush=True)
        elif entry["status"] == "skipped":
            skipped += 1
            print(f"[send-all]    SKIPPED ({entry.get('reason')})", flush=True)
        else:
            failed += 1
            print(f"[send-all]    FAILED @ {entry.get('stage')}: {entry.get('error', '')[:100]}",
                  file=sys.stderr)

    # Cleanup per-user email files
    for user in users:
        email_file = Path(PATHS["email"].format(user_id=user["id"]))
        email_file.unlink(missing_ok=True)

    # Write run log
    date_str = payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    log_path = Path(PATHS["run_log"].format(date=date_str))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_log = {
        "date":        date_str,
        "run_at":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clear_day":   clear_day,
        "users_total": len(users),
        "sent":        sent,
        "failed":      failed,
        "skipped":     skipped,
        "entries":     log_entries,
    }
    log_path.write_text(json.dumps(run_log, indent=2), encoding="utf-8")

    print(json.dumps({
        "status":  "ok",
        "sent":    sent,
        "failed":  failed,
        "skipped": skipped,
        "run_log": str(log_path),
    }, indent=2))


if __name__ == "__main__":
    main()
