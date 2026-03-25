"""
Sonar — Telegram message listener.
Monitors incoming private messages from real users and sends email alerts via Resend.
"""

import os
import sys
import logging
import time
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import MessageService, User
from dotenv import load_dotenv
from crypto import encrypt_name
import requests

load_dotenv()

# --- Config ---
API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ALERT_TO = os.getenv("ALERT_TO_EMAIL")
ALERT_FROM = os.getenv("ALERT_FROM_EMAIL")
CIPHER_KEY = os.getenv("CIPHER_PASSPHRASE", "")

# --- Rate limiting ---
COOLDOWN_SECONDS = 600          # 10 minutes between emails
DAILY_LIMIT = 10                # Max emails per day
SGT = timezone(timedelta(hours=8))

_last_email_time = 0.0          # Timestamp of last email sent
_daily_count = 0                # Emails sent since last reset
_daily_reset_date = None        # The SGT date the counter applies to

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sonar")

# --- Telegram client ---
client = TelegramClient("sonar_session", API_ID, API_HASH)


def _check_daily_reset() -> None:
    """Reset the daily counter if we've passed 7 AM SGT."""
    global _daily_count, _daily_reset_date
    now_sgt = datetime.now(SGT)
    # The "alert day" starts at 7 AM SGT
    if now_sgt.hour >= 7:
        current_day = now_sgt.date()
    else:
        current_day = now_sgt.date() - timedelta(days=1)

    if _daily_reset_date != current_day:
        _daily_count = 0
        _daily_reset_date = current_day
        log.info(f"Daily email counter reset for {current_day}.")


def can_send_email() -> bool:
    """Check both cooldown and daily limit."""
    global _last_email_time
    _check_daily_reset()

    now = time.time()

    # Check cooldown
    elapsed = now - _last_email_time
    if elapsed < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - elapsed)
        log.info(f"Cooldown active — {remaining}s remaining. Email suppressed.")
        return False

    # Check daily limit
    if _daily_count >= DAILY_LIMIT:
        log.info(f"Daily limit reached ({DAILY_LIMIT}). Email suppressed.")
        return False

    return True


def send_email(subject: str, html_body: str) -> None:
    """Send an alert email via Resend."""
    global _last_email_time, _daily_count
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": f"Sonar <{ALERT_FROM}>",
                "to": [ALERT_TO],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )
        resp.raise_for_status()
        _last_email_time = time.time()
        _daily_count += 1
        log.info(f"Email sent successfully. ({_daily_count}/{DAILY_LIMIT} today)")
    except Exception as e:
        log.error(f"Failed to send email: {e}")


@client.on(events.NewMessage(incoming=True))
async def handler(event):
    """Process every incoming message and decide whether to alert."""

    # Ignore service messages (join notifications, group actions, etc.)
    if isinstance(event.message, MessageService):
        log.info("Ignored service message.")
        return

    # Only care about private (1-to-1) chats
    if not event.is_private:
        log.info("Ignored non-private message.")
        return

    # Get sender entity
    sender = await event.get_sender()

    # Ignore bots
    if not isinstance(sender, User) or sender.bot:
        log.info("Ignored bot or non-user sender.")
        return

    # Ignore Telegram's own service account (notifications, OTPs, etc.)
    if sender.id == 777000:
        log.info("Ignored Telegram service account.")
        return

    # --- Build and send alert ---
    sender_name = (sender.first_name or "") + (" " + sender.last_name if sender.last_name else "")
    sender_name = sender_name.strip() or "Unknown"

    log.info(f"Alert triggered — private message from user ID {sender.id}")

    # Check rate limits before sending
    if not can_send_email():
        return

    subject = "Echo"

    decrypt_url = "http://161.35.122.12:8080/decrypt.html"

    if CIPHER_KEY:
        encrypted = encrypt_name(sender_name, CIPHER_KEY)
        body = f'{encrypted}<br><br><a href="{decrypt_url}">Authenticate</a>'
    else:
        body = f'You have a new private message on Telegram.<br><br><a href="{decrypt_url}">Authenticate</a>'

    send_email(subject, body)


async def main():
    log.info("Sonar starting...")
    await client.start(phone=PHONE)
    log.info("Connected to Telegram. Listening for messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
