# Sonar

A personal Telegram monitoring service. Sonar listens for incoming private messages on a Telegram account and sends email alerts via the Resend API. Designed for a Telegram account tied to a device that isn't always at hand — the email notification acts as a bridge so you know when to check.

The sender's name is lightly encrypted in the email body using a XOR cipher, obscuring it from casual observers. A self-hosted decryption tool allows you to reveal the sender from your phone.

---

## Architecture

```
Telegram Cloud
    │
    ▼
Telethon (persistent session on VPS)
    │
    ├── Incoming private message from a real user
    │       │
    │       ▼
    │   Filter logic (reject bots, service messages, non-private chats)
    │       │
    │       ▼
    │   Encrypt sender name (XOR + Base64)
    │       │
    │       ▼
    │   Send HTML email via Resend API
    │       │
    │       ▼
    │   Email arrives in inbox
    │       • Subject: "Echo"
    │       • Sender display: "Sonar"
    │       • Body: cipher text + link to decryptor
    │
    └── Weekly heartbeat (cron)
            │
            ▼
        Validate systemd service is active
        Validate Telegram session is authorized
            │
            ▼
        Send status email via Resend API
```

### How Telethon works

Telegram offers two types of API access: Bot API (for bot accounts) and User API (for personal accounts). Sonar uses the User API via Telethon, a Python client library, because it needs to monitor messages arriving at a personal account — something bot accounts cannot do.

On first run, Telethon authenticates using an OTP sent to the Telegram app and (if enabled) a two-step verification password. This creates a `.session` file on the server that persists the login. Subsequent runs reuse this session without further authentication.

The client maintains a persistent connection to Telegram's servers and receives events in real time — there is no polling or scheduled checking.

---

## Project structure

```
sonar/
├── .env.example        # Template for environment variables
├── .gitignore          # Excludes .env, .session files, venv/
├── README.md
├── sonar.py            # Main Telegram listener
├── crypto.py           # XOR + Base64 encrypt/decrypt helpers
├── heartbeat.py        # Weekly health check script
├── decrypt.html        # Browser-based decryption tool (self-contained)
├── sonar.service       # systemd unit file
└── requirements.txt    # Python dependencies
```

---

## Components

### sonar.py — Message listener

The core service. Connects to Telegram as a user client and listens for all incoming messages. Each message passes through a filter chain:

1. **Service messages** — rejected. These are structural events like join notifications, group creation, and pin actions. They arrive as `MessageService` types in Telethon.
2. **Non-private messages** — rejected. Only 1-to-1 direct messages trigger alerts. Group and channel messages are ignored.
3. **Bot accounts** — rejected. Telegram explicitly flags bot accounts via the `User.bot` attribute.
4. **Telegram service account (ID 777000)** — rejected. This is Telegram's own account that delivers OTPs, login notifications, and system messages.

Messages that survive all filters trigger an email. The sender's display name is encrypted with the XOR cipher and included in the email body as cipher text. The email also contains a link to the self-hosted decryption page.

### crypto.py — Encryption helpers

Provides `encrypt_name()` and `decrypt_name()` functions. The cipher works by XOR-ing each character of the sender's name with a repeating passphrase, then Base64-encoding the result (URL-safe variant).

This is intentionally lightweight — not cryptographically secure. Its only purpose is to prevent a casual observer browsing the inbox from immediately seeing contact names. The passphrase is stored in `.env` on the server and carried in the operator's memory for decryption.

### heartbeat.py — Weekly health check

A standalone script designed to run via cron. It performs two checks:

1. **systemd service status** — runs `systemctl is-active sonar` to confirm the listener process hasn't crashed or entered a failed state.
2. **Telegram session validity** — opens a second Telethon connection using the existing session file, calls `get_me()` to verify the session is still authorized and the Telegram API is reachable, then disconnects.

The email subject reflects the outcome: "Sonar — Heartbeat OK" if both checks pass, or "Sonar — Heartbeat ALERT" if either fails. The body includes a two-line status report.

### decrypt.html — Decryption tool

A single self-contained HTML file with embedded CSS and JavaScript. No external dependencies, no network requests. The user pastes cipher text from the alert email, enters the passphrase, and the sender name is revealed — all computation happens locally in the browser.

Hosted on the VPS via Caddy and accessible from a phone browser.

---

## Environment variables

Stored in `.env` on the server (never committed to Git):

| Variable | Description |
|---|---|
| `TELEGRAM_API_ID` | From my.telegram.org |
| `TELEGRAM_API_HASH` | From my.telegram.org |
| `TELEGRAM_PHONE` | Phone number with country code (e.g. +65...) |
| `RESEND_API_KEY` | Resend API key |
| `ALERT_TO_EMAIL` | Destination email for alerts |
| `ALERT_FROM_EMAIL` | Verified sender address in Resend |
| `CIPHER_PASSPHRASE` | XOR passphrase (memorize this) |

---

## Server configuration

Sonar runs on a DigitalOcean VPS shared with other projects. The three server-side components are managed independently.

### systemd service

The listener runs as a systemd service for automatic restarts and boot persistence. The unit file (`sonar.service`) is copied to `/etc/systemd/system/`.

Key properties:
- `Restart=on-failure` with a 10-second delay — if the process crashes, systemd brings it back automatically
- `PYTHONUNBUFFERED=1` — ensures log output appears immediately in journalctl rather than being buffered
- `After=network.target` — waits for network availability before starting

**Commands:**
```bash
# Check status
systemctl status sonar

# View recent logs
journalctl -u sonar -n 20

# Restart (e.g. after a code update)
systemctl restart sonar

# Stop
systemctl stop sonar

# Enable/disable boot persistence
systemctl enable sonar
systemctl disable sonar
```

### Cron job

The heartbeat runs via crontab:

```
0 1 * * 6 cd /root/sonar && /root/sonar/venv/bin/python heartbeat.py
```

This fires every Saturday at 01:00 UTC (09:00 SGT). The `cd` ensures the working directory is correct so the `.env` and `.session` files are found.

**Commands:**
```bash
# View crontab
crontab -l

# Edit crontab
crontab -e
```

### Caddy (web server)

Caddy serves the `decrypt.html` page as a static file. It runs on a dedicated port to avoid interfering with other projects on the same server. The relevant block in `/etc/caddy/Caddyfile`:

```
:8080 {
    root * /var/www/html
    file_server
}
```

The decrypt page is copied to `/var/www/html/decrypt.html`. Port 8080 must be open in the firewall (`ufw allow 8080`).

**Commands:**
```bash
# Reload after Caddyfile changes
systemctl reload caddy

# Check Caddy status
systemctl status caddy

# Update the hosted decrypt page after changes
cp ~/sonar/decrypt.html /var/www/html/decrypt.html
```

---

## Development workflow

Code is edited locally and deployed to the server via Git:

```bash
# Local — make changes, commit, push
cd ~/Projects/sonar
git add .
git commit -m "description of change"
git push

# Server — pull and restart
ssh root@<server-ip>
cd ~/sonar
git pull
systemctl restart sonar
```

If `decrypt.html` is modified, also update the hosted copy:

```bash
cp ~/sonar/decrypt.html /var/www/html/decrypt.html
```

---

## Dependencies

| Package | Purpose |
|---|---|
| telethon | Telegram user client (async, persistent connection) |
| python-dotenv | Load .env file into environment |
| requests | HTTP client for Resend API calls |

---

## Session management

The `.session` file created by Telethon is a SQLite database containing the authenticated Telegram session. It should be treated as a credential:

- It is excluded from Git via `.gitignore`
- If deleted, re-authentication with a new OTP (and 2FA password if enabled) is required
- Active sessions can be viewed and revoked in the Telegram app under Settings → Devices
- The file is only usable from the server where it was created

---

## Filtering rationale

The goal is to alert only on messages that require human attention — a real person reaching out privately. Everything else is noise:

- **Bots** send automated content (verification codes, notifications, RSS feeds) that doesn't need an immediate response
- **Service messages** are structural events (user joined, chat created, message pinned) generated by Telegram itself
- **Group/channel messages** are high-volume and rarely urgent for a single recipient
- **Telegram account 777000** is Telegram's internal service account used for OTPs and login alerts
