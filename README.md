# Sonar

Telegram personal message monitor. Sends email alerts via Resend when a real user sends a private message.

## Components

- **sonar.py** — Persistent Telegram listener (runs as systemd service)
- **heartbeat.py** — Weekly "alive" check (runs via cron)
- **decrypt.html** — Phone-side tool to decrypt sender names from alert emails
- **crypto.py** — Lightweight XOR + Base64 cipher helpers

## Setup

1. Get Telegram API credentials from https://my.telegram.org
2. Copy `.env.example` to `.env` and fill in values
3. `pip install -r requirements.txt`
4. Run `python sonar.py` (first run requires OTP from Telegram)
5. Deploy as systemd service for persistence

## Filtering

Only alerts on private messages from real (non-bot) users. Ignores:
- Bot accounts
- Telegram service messages (join notifications, OTPs)
- Group/channel messages
- Service account (ID 777000)
