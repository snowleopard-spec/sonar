"""
Sonar Heartbeat — weekly health check via Resend.
Validates that the Sonar systemd service is active and the Telegram
session is connected, then reports status by email.
Intended to be run by cron every Saturday morning.
"""

import os
import sys
import subprocess
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import RPCError

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ALERT_TO = os.getenv("ALERT_TO_EMAIL")
ALERT_FROM = os.getenv("ALERT_FROM_EMAIL")

SERVICE_NAME = "sonar"


def check_service_active() -> tuple[bool, str]:
    """Check if the sonar systemd service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True, text=True, timeout=5,
        )
        status = result.stdout.strip()
        return status == "active", status
    except Exception as e:
        return False, str(e)


async def check_telegram_session() -> tuple[bool, str]:
    """Open the existing session read-only and verify we can reach Telegram."""
    client = TelegramClient("sonar_session", API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return False, "Session not authorized"
        # Lightweight API call to confirm connectivity
        me = await client.get_me()
        return True, f"Connected as {me.first_name} (ID {me.id})"
    except RPCError as e:
        return False, f"Telegram RPC error: {e}"
    except Exception as e:
        return False, f"Connection error: {e}"
    finally:
        await client.disconnect()


def send_email(subject: str, body: str) -> None:
    """Send the heartbeat email via Resend."""
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": ALERT_FROM,
            "to": [ALERT_TO],
            "subject": subject,
            "text": body,
        },
        timeout=10,
    )
    resp.raise_for_status()


async def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Run checks ---
    svc_ok, svc_detail = check_service_active()
    tg_ok, tg_detail = check_telegram_session()

    all_ok = svc_ok and tg_ok

    # --- Build report ---
    checks = [
        f"  Service (systemd):  {'OK' if svc_ok else 'FAIL'} — {svc_detail}",
        f"  Telegram session:   {'OK' if tg_ok else 'FAIL'} — {tg_detail}",
    ]
    report = "\n".join(checks)

    if all_ok:
        subject = "Sonar — Heartbeat OK"
        body = f"All checks passed at {now}.\n\n{report}"
    else:
        subject = "Sonar — Heartbeat ALERT"
        body = f"One or more checks failed at {now}.\n\n{report}"

    # --- Send ---
    try:
        send_email(subject, body)
        print(f"Heartbeat sent at {now} — {'OK' if all_ok else 'ISSUES DETECTED'}")
    except Exception as e:
        print(f"Heartbeat email failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
