#!/usr/bin/env python3
"""
manage_users.py — WAT Framework Tool
CLI for managing Forex Factory Alert subscribers (backed by Supabase).

Usage:
    python tools/manage_users.py --add --name "Alice" --email "a@gmail.com" --instruments "EURUSD,XAUUSD" --timezone ET
    python tools/manage_users.py --list
    python tools/manage_users.py --update --email "a@gmail.com" --instruments "EURUSD,GBPUSD"
    python tools/manage_users.py --update-tz --email "a@gmail.com" --timezone IST
    python tools/manage_users.py --deactivate --email "a@gmail.com"
    python tools/manage_users.py --activate --email "a@gmail.com"
    python tools/manage_users.py --validate-instruments "EURUSD,FAKEPAIR,XAUUSD"

Accepted --timezone values (short codes or full IANA names):
    ET / EST   → America/New_York       IST        → Asia/Kolkata
    CT / CST   → America/Chicago        SGT        → Asia/Singapore
    MT / MST   → America/Denver         JST        → Asia/Tokyo
    PT / PST   → America/Los_Angeles    AEST/AEDT  → Australia/Sydney
    GMT / UTC  → UTC                    BST/WET    → Europe/London
    CET/CEST   → Europe/Paris           HKT        → Asia/Hong_Kong
    MSK        → Europe/Moscow          BRT        → America/Sao_Paulo
    GST        → Asia/Dubai             PKT        → Asia/Karachi

Exit codes:
    0 — success
    1 — argument or validation error
    2 — Supabase error
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VALID_INSTRUMENTS, TIMEZONE_ALIASES

import pytz


# ── Supabase client ───────────────────────────────────────────────────────────

def get_supabase():
    try:
        from supabase import create_client
    except ImportError:
        print(json.dumps({"error": "supabase package not installed. Run: pip install supabase"}),
              file=sys.stderr)
        sys.exit(2)

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        print(json.dumps({"error": "SUPABASE_URL and SUPABASE_KEY must be set in .env"}),
              file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_timezone(raw: str) -> str:
    """Accept short alias (ET, IST …) or full IANA name. Returns canonical IANA string."""
    upper = raw.strip().upper()
    if upper in TIMEZONE_ALIASES:
        return TIMEZONE_ALIASES[upper]
    # Accept full IANA name (e.g. "America/New_York")
    try:
        pytz.timezone(raw.strip())
        return raw.strip()
    except pytz.UnknownTimeZoneError:
        aliases = ", ".join(sorted(TIMEZONE_ALIASES.keys()))
        print(json.dumps({
            "error": f"Unknown timezone: '{raw}'",
            "accepted_short_codes": aliases,
            "tip": "Full IANA names like 'America/New_York' are also accepted",
        }), file=sys.stderr)
        sys.exit(1)


def validate_instruments(raw: str) -> list[str]:
    items = [i.strip().upper() for i in raw.split(",") if i.strip()]
    if not items:
        print(json.dumps({"error": "No instruments provided"}), file=sys.stderr)
        sys.exit(1)
    invalid = [i for i in items if i not in VALID_INSTRUMENTS]
    if invalid:
        print(json.dumps({
            "error": f"Unknown instruments: {invalid}",
            "valid_examples": sorted(VALID_INSTRUMENTS)[:20],
        }), file=sys.stderr)
        sys.exit(1)
    return sorted(set(items))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args: argparse.Namespace) -> None:
    instruments = validate_instruments(args.instruments)
    tz_iana = resolve_timezone(args.timezone)
    ts = now_iso()
    sb = get_supabase()

    record = {
        "name":        args.name,
        "email":       args.email.lower(),
        "instruments": ",".join(instruments),
        "timezone":    tz_iana,
        "active":      True,
        "created_at":  ts,
        "updated_at":  ts,
        "notes":       args.notes,
    }

    try:
        result = sb.table("users").insert(record).execute()
    except Exception as exc:
        msg = str(exc)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            print(json.dumps({"error": f"Email already exists: {args.email}"}), file=sys.stderr)
        else:
            print(json.dumps({"error": f"Supabase insert failed: {msg}"}), file=sys.stderr)
        sys.exit(2)

    print(json.dumps({
        "status":      "added",
        "name":        args.name,
        "email":       args.email.lower(),
        "instruments": instruments,
        "timezone":    tz_iana,
    }, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    sb = get_supabase()
    try:
        if args.all:
            result = sb.table("users").select("*").order("id").execute()
        else:
            result = sb.table("users").select("*").eq("active", True).order("id").execute()
    except Exception as exc:
        print(json.dumps({"error": f"Supabase query failed: {exc}"}), file=sys.stderr)
        sys.exit(2)

    users = result.data or []
    print(json.dumps({"count": len(users), "users": users}, indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    instruments = validate_instruments(args.instruments)
    ts = now_iso()
    sb = get_supabase()

    try:
        result = (
            sb.table("users")
            .update({"instruments": ",".join(instruments), "updated_at": ts})
            .eq("email", args.email.lower())
            .execute()
        )
    except Exception as exc:
        print(json.dumps({"error": f"Supabase update failed: {exc}"}), file=sys.stderr)
        sys.exit(2)

    if not result.data:
        print(json.dumps({"error": f"No user found with email: {args.email}"}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({
        "status":      "updated",
        "email":       args.email.lower(),
        "instruments": instruments,
    }, indent=2))


def cmd_update_tz(args: argparse.Namespace) -> None:
    tz_iana = resolve_timezone(args.timezone)
    ts = now_iso()
    sb = get_supabase()

    try:
        result = (
            sb.table("users")
            .update({"timezone": tz_iana, "updated_at": ts})
            .eq("email", args.email.lower())
            .execute()
        )
    except Exception as exc:
        print(json.dumps({"error": f"Supabase update failed: {exc}"}), file=sys.stderr)
        sys.exit(2)

    if not result.data:
        print(json.dumps({"error": f"No user found with email: {args.email}"}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({
        "status":   "timezone_updated",
        "email":    args.email.lower(),
        "timezone": tz_iana,
    }, indent=2))


def cmd_deactivate(args: argparse.Namespace) -> None:
    ts = now_iso()
    sb = get_supabase()

    try:
        result = (
            sb.table("users")
            .update({"active": False, "updated_at": ts})
            .eq("email", args.email.lower())
            .execute()
        )
    except Exception as exc:
        print(json.dumps({"error": f"Supabase update failed: {exc}"}), file=sys.stderr)
        sys.exit(2)

    if not result.data:
        print(json.dumps({"error": f"No user found: {args.email}"}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"status": "deactivated", "email": args.email.lower()}, indent=2))


def cmd_activate(args: argparse.Namespace) -> None:
    ts = now_iso()
    sb = get_supabase()

    try:
        result = (
            sb.table("users")
            .update({"active": True, "updated_at": ts})
            .eq("email", args.email.lower())
            .execute()
        )
    except Exception as exc:
        print(json.dumps({"error": f"Supabase update failed: {exc}"}), file=sys.stderr)
        sys.exit(2)

    if not result.data:
        print(json.dumps({"error": f"No user found: {args.email}"}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"status": "activated", "email": args.email.lower()}, indent=2))


def cmd_validate(args: argparse.Namespace) -> None:
    instruments = validate_instruments(args.validate_instruments)
    print(json.dumps({"valid": True, "instruments": instruments}, indent=2))


# ── Arg parser ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage Forex Factory Alert subscribers (Supabase-backed).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Timezone short codes accepted:
  ET/EST   → America/New_York    IST  → Asia/Kolkata
  CT/CST   → America/Chicago     SGT  → Asia/Singapore
  MT/MST   → America/Denver      JST  → Asia/Tokyo
  PT/PST   → America/Los_Angeles HKT  → Asia/Hong_Kong
  GMT/UTC  → UTC                 AEST → Australia/Sydney
  BST/WET  → Europe/London       MSK  → Europe/Moscow
  CET/CEST → Europe/Paris        BRT  → America/Sao_Paulo
  GST      → Asia/Dubai          PKT  → Asia/Karachi
Full IANA names (e.g. America/New_York) are also accepted.
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add",       action="store_true", help="Add a new subscriber")
    group.add_argument("--list",      action="store_true", help="List subscribers")
    group.add_argument("--update",    action="store_true", help="Update subscriber instruments")
    group.add_argument("--update-tz", action="store_true", help="Update subscriber timezone")
    group.add_argument("--deactivate",action="store_true", help="Deactivate a subscriber")
    group.add_argument("--activate",  action="store_true", help="Re-activate a subscriber")
    group.add_argument("--validate-instruments", metavar="INSTRUMENTS",
                       help="Validate a comma-separated instruments string")

    parser.add_argument("--name",       help="Subscriber full name (required for --add)")
    parser.add_argument("--email",      help="Subscriber email")
    parser.add_argument("--instruments",help='Comma-separated instruments, e.g. "EURUSD,XAUUSD"')
    parser.add_argument("--timezone",   help='Trading timezone, e.g. ET, IST, SGT, UTC (required for --add)')
    parser.add_argument("--notes",      default=None, help="Optional admin note")
    parser.add_argument("--all",        action="store_true", help="With --list: show inactive users too")

    args = parser.parse_args()

    if args.add:
        for field in ("name", "email", "instruments", "timezone"):
            if not getattr(args, field):
                parser.error(f"--add requires --{field.replace('_', '-')} "
                             f"(e.g. --timezone ET  or  --timezone IST)")
    if args.update or args.deactivate or args.activate or getattr(args, "update_tz", False):
        if not args.email:
            parser.error("--email is required")
    if args.update and not args.instruments:
        parser.error("--update requires --instruments")
    if getattr(args, "update_tz", False) and not args.timezone:
        parser.error("--update-tz requires --timezone")

    return args


def main() -> None:
    args = parse_args()
    if args.add:
        cmd_add(args)
    elif args.list:
        cmd_list(args)
    elif args.update:
        cmd_update(args)
    elif getattr(args, "update_tz", False):
        cmd_update_tz(args)
    elif args.deactivate:
        cmd_deactivate(args)
    elif args.activate:
        cmd_activate(args)
    elif args.validate_instruments:
        cmd_validate(args)


if __name__ == "__main__":
    main()
