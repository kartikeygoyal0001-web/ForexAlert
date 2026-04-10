#!/usr/bin/env python3
"""
run_morning_alert.py — WAT Framework Tool
Master orchestrator for the Forex Factory Morning Alert pipeline.
This is the single entry point called by Windows Task Scheduler.

Pipeline:
  1. Weekend check → exit silently if Sat/Sun
  2. fetch_ff_events.py       → .tmp/ff_events_raw.json
  3. filter_events_today.py   → .tmp/ff_events_today.json
  4. fetch_event_news.py      → .tmp/event_news_context.json [skipped if clear_day, non-fatal]
  5. generate_all_analyses.py → .tmp/analyses.json           [skipped if clear_day]
  6. send_all_emails.py       → sends HTML emails + run log

Usage:
    python tools/run_morning_alert.py
    python tools/run_morning_alert.py --dry-run   (runs pipeline but skips send step)

Exit codes:
    0 — success or weekend skip
    1 — fatal pipeline failure (emails not sent)
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

ROOT = Path(__file__).parent.parent
TOOLS = Path(__file__).parent

# Ordered pipeline steps
# NOTE: No bulk send step here — emails are sent per-user at their chosen time
#       by the separate ForexSendDue task (runs every 30 min via send_due_emails.py)
STEPS = [
    ("fetch",   "fetch_ff_events.py"),
    ("filter",  "filter_events_today.py"),
    ("news",    "fetch_event_news.py"),       # Tavily/Firecrawl enrichment (non-fatal)
    ("analyze", "generate_all_analyses.py"),
]

SKIP_ON_CLEAR_DAY = {"news", "analyze"}

# Only fetch and filter are fatal — all other steps log failure and continue
FATAL_STEPS = {"fetch", "filter"}


def run_step(name: str, script: str, extra_args: list[str] | None = None) -> tuple[int, str, str]:
    """Run a tool script. Returns (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(TOOLS / script)] + (extra_args or [])
    print(f"\n{'='*60}", flush=True)
    print(f"[{name.upper()}] Running: {script}", flush=True)
    print(f"{'='*60}", flush=True)

    result = subprocess.run(cmd, capture_output=False, text=True, cwd=str(ROOT))
    return result.returncode, "", ""


def run_step_captured(name: str, script: str, extra_args: list[str] | None = None) -> tuple[int, str, str]:
    """Run a tool script with captured output. Returns (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(TOOLS / script)] + (extra_args or [])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    return result.returncode, result.stdout, result.stderr


def send_admin_alert(subject: str, message: str) -> None:
    """Log admin alert. In production, wire this to an email send."""
    admin_email = os.getenv("ADMIN_EMAIL", "")
    print(f"\n[ADMIN ALERT] To: {admin_email}", file=sys.stderr)
    print(f"[ADMIN ALERT] Subject: {subject}", file=sys.stderr)
    print(f"[ADMIN ALERT] {message}", file=sys.stderr)


def is_weekend() -> bool:
    return datetime.now(timezone.utc).weekday() >= 5  # 5=Saturday, 6=Sunday


def load_filter_result() -> dict:
    path = ROOT / ".tmp" / "ff_events_today.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Forex Factory Morning Alert pipeline.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pipeline but skip the email send step")
    parser.add_argument("--force-weekend", action="store_true",
                        help="Skip weekend check (for testing)")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    print(f"\n{'#'*60}", flush=True)
    print(f"# Forex Factory Morning Alert - {date_str}", flush=True)
    print(f"# Run started: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}", flush=True)
    print(f"{'#'*60}\n", flush=True)

    # ── Weekend check ────────────────────────────────────────────────────────
    if not args.force_weekend and is_weekend():
        day_name = now.strftime("%A")
        print(f"[orchestrator] Today is {day_name} — no forex markets, skipping.", flush=True)
        sys.exit(0)

    clear_day = False
    pipeline_log = {
        "date": date_str,
        "run_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": args.dry_run,
        "steps": {},
    }

    for step_name, script in STEPS:
        # Skip non-essential steps on clear day
        if clear_day and step_name in SKIP_ON_CLEAR_DAY:
            print(f"[{step_name}] SKIPPED (clear day)", flush=True)
            pipeline_log["steps"][step_name] = "skipped_clear_day"
            continue

        # (dry-run flag preserved for future use — no send step in pipeline)

        # Run step (with live output for visibility)
        rc = run_step(step_name, script)[0]

        if rc == 0:
            pipeline_log["steps"][step_name] = "ok"
            print(f"[{step_name}] OK", flush=True)
        else:
            pipeline_log["steps"][step_name] = f"failed (exit {rc})"
            print(f"[{step_name}] FAILED (exit code {rc})", file=sys.stderr)

            # Fatal steps: fetch and filter — cannot continue
            if step_name in FATAL_STEPS:
                msg = f"Pipeline aborted: {step_name} failed with exit code {rc}"
                print(f"[orchestrator] FATAL: {msg}", file=sys.stderr)
                send_admin_alert(
                    f"[Forex Alert] Pipeline FAILED — {date_str}",
                    msg,
                )
                pipeline_log["status"] = "fatal"
                _write_pipeline_log(pipeline_log)
                sys.exit(1)

            # Non-fatal steps: log and continue
            print(f"[{step_name}] Non-fatal failure — continuing pipeline", flush=True)
            if step_name == "news":
                print(f"[news] Analysis will proceed without live news enrichment", flush=True)

        # After filter step: check clear_day flag
        if step_name == "filter":
            filter_result = load_filter_result()
            clear_day = filter_result.get("clear_day", False)
            if clear_day:
                print(f"[filter] Clear day detected — analysis/charts/pdf will be skipped", flush=True)

    pipeline_log["status"] = "completed"
    pipeline_log["run_end"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_pipeline_log(pipeline_log)

    print(f"\n{'#'*60}", flush=True)
    print(f"# Pipeline complete - {date_str}", flush=True)
    print(f"# Check .tmp/run_log_{date_str}.json for delivery details", flush=True)
    print(f"{'#'*60}\n", flush=True)


def _write_pipeline_log(log: dict) -> None:
    date_str = log.get("date", get_date_str())
    log_path = ROOT / ".tmp" / f"pipeline_log_{date_str}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"[orchestrator] Pipeline log: {log_path}", flush=True)


if __name__ == "__main__":
    main()
