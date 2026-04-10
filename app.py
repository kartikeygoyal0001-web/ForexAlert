"""
app.py — Flask frontend for Forex Factory Alert signup.
Run: python app.py
Then open: http://localhost:5000
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))
from config import TIMEZONE_ALIASES, VALID_INSTRUMENTS

app = Flask(__name__)


# ── Instrument groups for the UI ──────────────────────────────────────────────
INSTRUMENT_GROUPS = [
    ("Majors",      ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]),
    ("Metals",      ["XAUUSD", "XAGUSD"]),
    ("Indices",     ["US30", "NAS100", "SPX500"]),
    ("EUR Crosses", ["EURGBP", "EURJPY", "EURCAD", "EURAUD", "EURNZD", "EURCHF"]),
    ("GBP Crosses", ["GBPJPY", "GBPCAD", "GBPAUD", "GBPNZD", "GBPCHF"]),
    ("JPY Crosses", ["AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"]),
    ("Other",       ["AUDCAD", "AUDNZD", "NZDCAD", "NZDCHF", "AUDCHF", "USDCNH"]),
]

# ── Timezone options (code, label, offset) ────────────────────────────────────
TIMEZONE_OPTIONS = [
    ("ET",   "Eastern — New York",      "UTC-5/4"),
    ("CT",   "Central — Chicago",       "UTC-6/5"),
    ("MT",   "Mountain — Denver",       "UTC-7/6"),
    ("PT",   "Pacific — Los Angeles",   "UTC-8/7"),
    ("GMT",  "GMT / UTC",               "UTC±0"),
    ("BST",  "London (Summer)",         "UTC+1"),
    ("CET",  "Central Europe — Paris",  "UTC+1/2"),
    ("MSK",  "Moscow",                  "UTC+3"),
    ("GST",  "Gulf — Dubai",            "UTC+4"),
    ("PKT",  "Pakistan — Karachi",      "UTC+5"),
    ("IST",  "India — Kolkata",         "UTC+5:30"),
    ("SGT",  "Singapore",               "UTC+8"),
    ("HKT",  "Hong Kong",               "UTC+8"),
    ("JST",  "Japan — Tokyo",           "UTC+9"),
    ("AEST", "Australia — Sydney",      "UTC+10/11"),
    ("BRT",  "Brazil — São Paulo",      "UTC-3"),
]


def get_supabase():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_todays_report(user_id: int, name: str, email: str,
                       instruments: list[str], tz_iana: str) -> None:
    """If today's analyses already exist, immediately render and send today's report."""
    root = Path(__file__).parent
    analyses_path = root / ".tmp" / "analyses.json"
    if not analyses_path.exists():
        return  # Pipeline hasn't run today yet — user will get tomorrow's email

    tmp_dir = root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    html_path = tmp_dir / f"email_{user_id}.html"

    user_record = {
        "id":          user_id,
        "name":        name,
        "email":       email,
        "instruments": ",".join(instruments),
        "timezone":    tz_iana,
    }

    import json
    render_tool = root / "tools" / "render_email.py"
    send_tool   = root / "tools" / "send_gmail.py"

    render_result = subprocess.run(
        [sys.executable, str(render_tool),
         "--user-json", json.dumps(user_record),
         "--analyses",  str(analyses_path),
         "--output",    str(html_path)],
        capture_output=True, text=True, cwd=str(root),
    )
    if render_result.returncode != 0 or not html_path.exists():
        return

    try:
        from datetime import date
        date_str = date.today().strftime("%Y-%m-%d")
        subprocess.run(
            [sys.executable, str(send_tool),
             "--to",        email,
             "--subject",   f"Forex Alert: Today's High-Impact Events — {date_str}",
             "--html-file", str(html_path)],
            capture_output=True, text=True, cwd=str(root),
        )
    finally:
        html_path.unlink(missing_ok=True)


def send_welcome_email(name: str, email: str, instruments: list[str],
                       tz_code: str, alert_time: str) -> None:
    """Render and send a welcome confirmation email via send_gmail.py."""
    instrument_chips = "".join(
        f'<span style="display:inline-block;background:#e8f4fd;color:#1a6bb5;'
        f'font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px;margin:2px;">'
        f'{i}</span>'
        for i in instruments
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Welcome to Forex Morning Alert</title></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;color:#1a1a2e">
<div style="max-width:600px;margin:0 auto;background:#ffffff">

  <div style="background:#1a2130;padding:28px;border-radius:8px 8px 0 0">
    <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700">Forex Morning Alert</h1>
    <p style="margin:6px 0 0;color:#d9a621;font-size:13px">You're subscribed — welcome aboard</p>
  </div>

  <div style="padding:28px">
    <p style="font-size:15px;color:#1a1a2e;margin:0 0 20px">
      Hi <strong>{name}</strong>, you're all set. Here's a summary of your subscription:
    </p>

    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">
      <tr style="border-bottom:1px solid #e2e8f0">
        <td style="padding:10px 8px;color:#94a3b8;font-weight:700;width:140px">INSTRUMENTS</td>
        <td style="padding:10px 8px">{instrument_chips}</td>
      </tr>
      <tr style="border-bottom:1px solid #e2e8f0">
        <td style="padding:10px 8px;color:#94a3b8;font-weight:700">TIMEZONE</td>
        <td style="padding:10px 8px;color:#2d3748;font-weight:600">{tz_code}</td>
      </tr>
      <tr>
        <td style="padding:10px 8px;color:#94a3b8;font-weight:700">ALERT TIME</td>
        <td style="padding:10px 8px;color:#2d3748;font-weight:600">{alert_time} ({tz_code})</td>
      </tr>
    </table>

    <div style="background:#fffbeb;border-left:4px solid #d9a621;border-radius:0 6px 6px 0;
                padding:14px 16px;margin-bottom:24px;font-size:13px;color:#4a5568;line-height:1.6">
      💡 Your first briefing will arrive tomorrow morning. Each alert covers high-impact
      economic events filtered to your instruments, with AI analysis and beat/miss scenarios.
    </div>

    <p style="font-size:12px;color:#94a3b8;line-height:1.6;margin:0">
      Need to update your instruments or timezone? Visit
      <a href="{os.environ.get('APP_BASE_URL', 'http://localhost:5000')}/manage" style="color:#4a7cf4;">Manage Subscription</a>
      to edit preferences or cancel at any time.
    </p>
  </div>

  <div style="background:#f7fafc;padding:16px 28px;text-align:center;
              font-size:11px;color:#94a3b8;border-radius:0 0 8px 8px;border-top:1px solid #e2e8f0">
    Forex Morning Alert &nbsp;·&nbsp; Powered by OpenAI &nbsp;·&nbsp; Data: Forex Factory
  </div>
</div>
</body></html>"""

    root = Path(__file__).parent
    tmp_dir = root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    html_path = tmp_dir / f"welcome_{email.replace('@','_').replace('.','_')}.html"
    html_path.write_text(html, encoding="utf-8")

    send_tool = root / "tools" / "send_gmail.py"
    try:
        result = subprocess.run(
            [sys.executable, str(send_tool),
             "--to", email,
             "--subject", "Welcome to Forex Morning Alert — you're subscribed",
             "--html-file", str(html_path)],
            capture_output=True, text=True, cwd=str(root),
        )
        if result.returncode != 0:
            print(f"[send_gmail ERROR] stdout: {result.stdout!r}", flush=True)
            print(f"[send_gmail ERROR] stderr: {result.stderr!r}", flush=True)
        else:
            print(f"[send_gmail OK] {result.stdout.strip()}", flush=True)
    finally:
        html_path.unlink(missing_ok=True)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        instrument_groups=INSTRUMENT_GROUPS,
        timezone_options=TIMEZONE_OPTIONS,
        errors=[],
        form_data={},
    )


@app.route("/signup", methods=["POST"])
def signup():
    name        = request.form.get("name", "").strip()
    email       = request.form.get("email", "").strip().lower()
    instruments = request.form.getlist("instruments")
    tz_code     = request.form.get("timezone", "").strip().upper()
    alert_time  = request.form.get("alert_time", "").strip()
    newsletter  = request.form.get("newsletter")

    errors = []
    if not name:
        errors.append("Full name is required.")
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if not instruments:
        errors.append("Select at least one instrument you trade.")
    if not tz_code:
        errors.append("Please select your trading timezone.")
    if not alert_time:
        errors.append("Please choose your preferred alert time.")
    if not newsletter:
        errors.append("You must consent to receive the daily alert email.")

    if errors:
        return render_template(
            "index.html",
            instrument_groups=INSTRUMENT_GROUPS,
            timezone_options=TIMEZONE_OPTIONS,
            errors=errors,
            form_data=request.form,
        )

    # Validate and clean instruments
    valid_instruments = sorted({i for i in instruments if i in VALID_INSTRUMENTS})

    # Resolve timezone code → IANA name
    tz_iana = TIMEZONE_ALIASES.get(tz_code, tz_code)

    ts = now_iso()
    record = {
        "name":        name,
        "email":       email,
        "instruments": ",".join(valid_instruments),
        "timezone":    tz_iana,
        "alert_time":  alert_time,
        "active":      True,
        "created_at":  ts,
        "updated_at":  ts,
    }

    try:
        sb = get_supabase()
        result = sb.table("users").insert(record).execute()
        new_user_id = result.data[0]["id"] if result.data else 0
    except Exception as exc:
        msg = str(exc)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            errors.append("This email is already subscribed. Contact us to update your preferences.")
        else:
            errors.append(f"Registration failed — please try again. ({msg})")
        return render_template(
            "index.html",
            instrument_groups=INSTRUMENT_GROUPS,
            timezone_options=TIMEZONE_OPTIONS,
            errors=errors,
            form_data=request.form,
        )

    # Send welcome confirmation email (non-blocking — failure won't break signup)
    try:
        send_welcome_email(name, email, valid_instruments, tz_code, alert_time)
    except Exception:
        pass

    # Send today's report immediately if the pipeline has already run today
    try:
        send_todays_report(new_user_id, name, email, valid_instruments, tz_iana)
    except Exception:
        pass

    first_name = name.split()[0]
    return redirect(url_for("success", name=first_name))


@app.route("/success")
def success():
    name = request.args.get("name", "Trader")
    return render_template("success.html", name=name)


# ── Subscription management ───────────────────────────────────────────────────

def _iana_to_tz_code(iana: str) -> str:
    """Reverse-lookup: IANA name → short tz code (first match)."""
    for code, mapped in TIMEZONE_ALIASES.items():
        if mapped == iana:
            return code
    return iana  # Fallback to IANA string if no alias found


@app.route("/manage", methods=["GET", "POST"])
def manage():
    if request.method == "GET":
        return render_template("manage.html", user=None, errors=[], form_data={},
                               instrument_groups=[], timezone_options=[], selected_instruments=[])

    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        return render_template("manage.html", user=None, errors=["Please enter a valid email address."],
                               form_data=request.form, instrument_groups=[], timezone_options=[],
                               selected_instruments=[])

    try:
        sb = get_supabase()
        result = sb.table("users").select("*").eq("email", email).execute()
    except Exception as exc:
        return render_template("manage.html", user=None,
                               errors=[f"Lookup failed — please try again. ({exc})"],
                               form_data=request.form, instrument_groups=[], timezone_options=[],
                               selected_instruments=[])

    if not result.data:
        return render_template("manage.html", user=None,
                               errors=["No subscription found for that email address."],
                               form_data=request.form, instrument_groups=[], timezone_options=[],
                               selected_instruments=[])

    user = result.data[0]
    selected = [i.strip() for i in user.get("instruments", "").split(",") if i.strip()]
    tz_code = _iana_to_tz_code(user.get("timezone", ""))

    return render_template(
        "manage.html",
        user=user,
        user_tz_code=tz_code,
        selected_instruments=selected,
        instrument_groups=INSTRUMENT_GROUPS,
        timezone_options=TIMEZONE_OPTIONS,
        errors=[],
        flash=None,
        form_data={},
    )


@app.route("/manage/update", methods=["POST"])
def manage_update():
    email      = request.form.get("email", "").strip().lower()
    instruments = request.form.getlist("instruments")
    tz_code    = request.form.get("timezone", "").strip().upper()
    alert_time = request.form.get("alert_time", "").strip()

    errors = []
    if not instruments:
        errors.append("Select at least one instrument.")

    valid_instruments = sorted({i for i in instruments if i in VALID_INSTRUMENTS})
    tz_iana = TIMEZONE_ALIASES.get(tz_code, tz_code)

    if not errors:
        try:
            sb = get_supabase()
            result = (
                sb.table("users")
                .update({
                    "instruments": ",".join(valid_instruments),
                    "timezone":    tz_iana,
                    "alert_time":  alert_time,
                    "updated_at":  now_iso(),
                })
                .eq("email", email)
                .execute()
            )
            if not result.data:
                errors.append("No subscription found for that email.")
        except Exception as exc:
            errors.append(f"Update failed — please try again. ({exc})")

    # Re-fetch user to repopulate form
    try:
        sb = get_supabase()
        user_result = sb.table("users").select("*").eq("email", email).execute()
        user = user_result.data[0] if user_result.data else None
    except Exception:
        user = None

    if user is None:
        return render_template("manage.html", user=None,
                               errors=["Session expired — please look up your email again."],
                               form_data={}, instrument_groups=[], timezone_options=[],
                               selected_instruments=[])

    selected = [i.strip() for i in user.get("instruments", "").split(",") if i.strip()]
    tz_code_disp = _iana_to_tz_code(user.get("timezone", ""))

    return render_template(
        "manage.html",
        user=user,
        user_tz_code=tz_code_disp,
        selected_instruments=selected,
        instrument_groups=INSTRUMENT_GROUPS,
        timezone_options=TIMEZONE_OPTIONS,
        errors=errors,
        flash=None if errors else "Preferences updated successfully.",
        form_data={},
    )


@app.route("/manage/cancel", methods=["POST"])
def manage_cancel():
    email = request.form.get("email", "").strip().lower()
    try:
        sb = get_supabase()
        sb.table("users").delete().eq("email", email).execute()
    except Exception as exc:
        try:
            user_result = sb.table("users").select("*").eq("email", email).execute()
            user = user_result.data[0] if user_result.data else None
        except Exception:
            user = None
        return render_template("manage.html", user=user,
                               errors=[f"Cancellation failed — please try again. ({exc})"],
                               user_tz_code="", selected_instruments=[],
                               instrument_groups=INSTRUMENT_GROUPS,
                               timezone_options=TIMEZONE_OPTIONS, flash=None, form_data={})

    return render_template("manage.html", user=None, errors=[],
                           flash_global="Your subscription has been cancelled and your data removed. You can re-subscribe at any time.",
                           form_data={}, instrument_groups=[], timezone_options=[],
                           selected_instruments=[])


@app.route("/health")
def health():
    from flask import jsonify
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
