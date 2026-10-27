# Deploy on a Raspberry Pi

## What runs where

| Piece | Where |
|--------|--------|
| Aggregator (this repo’s `pi/`) | Raspberry Pi on the event LAN |
| **Public scoreboard** | **saintcon.org** — we only `PUT` JSON; we cannot change that website |
| Optional staff preview | Browser at `http://<pi-ip>:8080/` (LAN testing only; not for attendees) |

Game PCs only need to reach the Pi on the LAN. The Pi is the **only** box that talks to saintcon.org. Attendee / TV displays should use whatever URL saintcon gave you for the live board.

## Prerequisites

- Raspberry Pi OS (Bookworm or newer recommended)
- Python 3.11+
- Network: game PCs → Pi; Pi → internet (for saintcon.org)

## Install

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git

git clone <this-repo-url> ~/Scoreboard
cd ~/Scoreboard/pi

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config.example.env config.env
nano config.env
```

Auth needs no config: stations use `Authorization: Bearer <pi-ip>` (the Pi’s LAN IP).

For the public saintcon board, set:

```env
SCOREBOARD_PUSH_URL=https://saintcon.org/api/scoreboards/<id>
SCOREBOARD_PUSH_TOKEN=<key>
SCOREBOARD_PUSH_STATUS=live
SCOREBOARD_PUSH_MESSAGE=
```

Leave `SCOREBOARD_PUSH_URL` empty to run LAN-only (local board still works).

## Run once (smoke test)

```bash
cd ~/Scoreboard/pi
source .venv/bin/activate
python run.py
```

Open `http://<pi-ip>:8080/` and submit the example Orbit run (see README).

## systemd service

```bash
sudo tee /etc/systemd/system/terminal-relay-scoreboard.service >/dev/null <<'EOF'
[Unit]
Description=Terminal Relay Scoreboard Aggregator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Scoreboard/pi
Environment=PATH=/home/pi/Scoreboard/pi/.venv/bin
ExecStart=/home/pi/Scoreboard/pi/.venv/bin/python run.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now terminal-relay-scoreboard
sudo systemctl status terminal-relay-scoreboard
```

Adjust `User=` / paths if your home directory differs.

## Firewall

If `ufw` is enabled:

```bash
sudo ufw allow 8080/tcp
```

## Staff ops on event day

| Action | How |
|--------|-----|
| Watch **public** board | saintcon.org scoreboard URL (site we cannot edit) |
| Optional staff preview | `http://<pi-ip>:8080/` |
| Check health | `curl http://<pi-ip>:8080/health` |
| Reset board | `curl -X POST -H "Authorization: Bearer <pi-ip>" http://<pi-ip>:8080/api/v1/admin/reset` |
| Force saintcon push | `curl -X POST -H "Authorization: Bearer <pi-ip>" http://<pi-ip>:8080/api/v1/admin/push` |
| Persistence | SQLite at `pi/data/scoreboard.db` — reboot keeps scores |

## Notes

- Prefer a static LAN IP (DHCP reservation) for the Pi so game PCs have a stable target.
- TLS is optional on pure LAN; still use the bearer token. If anything leaves the LAN, put TLS in front (Caddy/nginx).
- saintcon allows at most one push per 15 seconds; the Pi debounces automatically.
