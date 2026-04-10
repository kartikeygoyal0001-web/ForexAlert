#!/usr/bin/env python3
"""
send_gmail.py — WAT Framework Tool
Sends an HTML email via the Gmail API using OAuth2 credentials.
Optionally attaches a PDF file.

Adapted from research_emailer/tools/send_gmail.py — adds --attach support
by switching to MIMEMultipart("mixed") when an attachment is provided.

Usage:
    python tools/send_gmail.py --to recipient@example.com \
                                --subject "Your Subject" \
                                --html-file .tmp/email_body.html

    python tools/send_gmail.py --to recipient@example.com \
                                --subject "Your Subject" \
                                --html-file .tmp/email_body.html \
                                --attach .tmp/report_2026-04-10.pdf

Exit codes:
    0 — success, JSON with message_id written to stdout
    1 — argument or file error
    2 — credentials/auth error
    3 — Gmail API error
"""

import argparse
import base64
import json
import os
import sys
import time
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path


_PROJECT_ROOT = Path(__file__).parent.parent  # repo root = app root

CREDENTIALS_FILE = str(_PROJECT_ROOT / "gmail_credentials.json")
TOKEN_FILE        = str(_PROJECT_ROOT / "token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send an HTML email (with optional PDF attachment) via Gmail API."
    )
    parser.add_argument("--to", required=True, dest="recipient", help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--html-file", required=True, dest="html_file",
                        help="Path to file containing the HTML body")
    parser.add_argument("--attach", default=None, dest="attachment",
                        help="Optional path to a PDF file to attach")
    return parser.parse_args()


def load_html(path: str) -> str:
    html_path = Path(path)
    if not html_path.exists():
        print(json.dumps({
            "error": f"HTML file not found: {path}",
            "fix": "Ensure the HTML was rendered before calling this tool",
        }), file=sys.stderr)
        sys.exit(1)
    if html_path.stat().st_size == 0:
        print(json.dumps({
            "error": f"HTML file is empty: {path}",
        }), file=sys.stderr)
        sys.exit(1)
    return html_path.read_text(encoding="utf-8")


def get_gmail_service():
    # ── Startup diagnostics (visible in Render logs) ──────────────────────────
    print(f"[send_gmail] PROJECT_ROOT : {_PROJECT_ROOT}", file=sys.stderr)
    print(f"[send_gmail] CREDENTIALS  : {CREDENTIALS_FILE}  exists={Path(CREDENTIALS_FILE).exists()}", file=sys.stderr)
    print(f"[send_gmail] TOKEN        : {TOKEN_FILE}  exists={Path(TOKEN_FILE).exists()}", file=sys.stderr)

    # Detect headless / server environment — browser-based OAuth will never work here
    is_headless = (
        os.environ.get("RENDER") == "true"
        or os.environ.get("CI") == "true"
        or not os.environ.get("DISPLAY", "")  # Linux without a display
    )

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print(json.dumps({
            "error": "Google API packages not installed",
            "fix": "Run: pip install -r requirements.txt",
        }), file=sys.stderr)
        sys.exit(2)

    creds = None

    if Path(TOKEN_FILE).exists():
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print(f"[send_gmail] token loaded — valid={creds.valid} expired={creds.expired}", file=sys.stderr)
        except Exception as exc:
            print(f"[send_gmail] WARNING: Could not load {TOKEN_FILE}: {exc}", file=sys.stderr)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[send_gmail] token refreshed successfully", file=sys.stderr)
            except Exception as exc:
                print(f"[send_gmail] Token refresh failed: {exc}", file=sys.stderr)
                creds = None

        if not creds:
            if is_headless:
                print(json.dumps({
                    "error": "No valid token and running in headless/server environment — cannot open browser for OAuth",
                    "fix": (
                        "Run the OAuth flow locally: python tools/send_gmail.py --to test@example.com "
                        "--subject test --html-file /dev/null  (this will open a browser). "
                        "Then re-upload the generated token.json to Render Secret Files."
                    ),
                }), file=sys.stderr)
                sys.exit(2)

            if not Path(CREDENTIALS_FILE).exists():
                print(json.dumps({
                    "error": f"{CREDENTIALS_FILE} not found",
                    "fix": "Upload gmail_credentials.json as a Render Secret File named 'gmail_credentials.json'",
                }), file=sys.stderr)
                sys.exit(2)

            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0, prompt="consent")
            except Exception as exc:
                print(json.dumps({
                    "error": f"OAuth flow failed: {exc}",
                    "fix": "Ensure gmail_credentials.json is valid and your browser can open",
                }), file=sys.stderr)
                sys.exit(2)

        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        except Exception as exc:
            print(f"Warning: Could not save {TOKEN_FILE}: {exc}", file=sys.stderr)

    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as exc:
        print(json.dumps({"error": f"Failed to build Gmail service: {exc}"}), file=sys.stderr)
        sys.exit(2)


def get_sender_email(service) -> str:
    try:
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "me")
    except Exception:
        return "me"


def build_message(sender: str, recipient: str, subject: str,
                  html_body: str, attachment_path: str | None) -> dict:
    if attachment_path:
        # Mixed: body + attachment
        msg = MIMEMultipart("mixed")
        msg["To"] = recipient
        msg["From"] = sender
        msg["Subject"] = subject

        # HTML body in an alternative part (best practice)
        alt = MIMEMultipart("alternative")
        html_part = MIMEText(html_body, "html", "utf-8")
        alt.attach(html_part)
        msg.attach(alt)

        # PDF attachment
        attach_path = Path(attachment_path)
        if not attach_path.exists():
            print(json.dumps({
                "error": f"Attachment not found: {attachment_path}",
            }), file=sys.stderr)
            sys.exit(1)

        with open(attach_path, "rb") as f:
            pdf_data = f.read()

        pdf_part = MIMEBase("application", "pdf")
        pdf_part.set_payload(pdf_data)
        encoders.encode_base64(pdf_part)
        pdf_part.add_header(
            "Content-Disposition",
            "attachment",
            filename=attach_path.name,
        )
        msg.attach(pdf_part)

    else:
        # Alternative only (HTML body, no attachment)
        msg = MIMEMultipart("alternative")
        msg["To"] = recipient
        msg["From"] = sender
        msg["Subject"] = subject
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    return {"raw": raw_b64}


def send_message(service, message: dict, retry: bool = False) -> str:
    try:
        result = service.users().messages().send(userId="me", body=message).execute()
        return result["id"]

    except Exception as exc:
        error_str = str(exc)

        if "429" in error_str and not retry:
            print("Gmail API rate limited. Retrying in 15 seconds...", file=sys.stderr)
            time.sleep(15)
            return send_message(service, message, retry=True)

        if "403" in error_str or "insufficientPermissions" in error_str:
            print(json.dumps({
                "error": "Gmail API permission denied",
                "fix": "Delete token.json and re-run to trigger fresh OAuth consent.",
            }), file=sys.stderr)
            sys.exit(3)

        if "400" in error_str:
            print(json.dumps({
                "error": f"Gmail API bad request: {error_str}",
                "fix": "Check that --to address is a valid email format",
            }), file=sys.stderr)
            sys.exit(3)

        print(json.dumps({"error": f"Gmail API send failed: {error_str}"}), file=sys.stderr)
        sys.exit(3)


def main() -> None:
    args = parse_args()
    html_body = load_html(args.html_file)
    service = get_gmail_service()
    sender = get_sender_email(service)
    message = build_message(sender, args.recipient, args.subject, html_body, args.attachment)
    message_id = send_message(service, message)

    result = {
        "status": "sent",
        "message_id": message_id,
        "to": args.recipient,
        "subject": args.subject,
        "from": sender,
        "has_attachment": args.attachment is not None,
    }
    if args.attachment:
        result["attachment"] = args.attachment

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
