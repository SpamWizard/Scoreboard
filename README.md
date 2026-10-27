# Terminal Relay Scoreboard

Live scoreboard pipeline for the **Terminal Relay** timed team game:

**Game PCs → Raspberry Pi (aggregator) → saintcon.org scoreboard (PUT only)**

This repo is **only** the Pi aggregator, shared score schema, and the client that pushes rankings to saintcon.org. It does **not** contain the game client, challenges, Kali/WSL, or baton firmware (those live in `Terminal-relay-software-in-the-big-26` / `baton_relay`).

### The public website is not in this repo

Attendees see the **saintcon.org** scoreboard. We do **not** own or change that site — no HTML, styling, or hosting here. The only integration they gave us is a replace-the-whole-board `PUT`:

```http
PUT https://saintcon.org/api/scoreboards/<id>
Authorization: Bearer <key>
```

This Pi service builds that JSON and pushes it when scores change. Whatever saintcon renders from `entries` is what the public sees.

```
[Game PC 1] --HTTP POST--> \
[Game PC 2] --HTTP POST-->  --> [Raspberry Pi] --PUT board.json--> [saintcon.org]
[Game PC N] --HTTP POST--> /         (optional: staff preview at :8080)
```

## Stack

- **Pi:** Python FastAPI + SQLite (origin of truth for rankings)
- **Public display:** saintcon.org only — fed by Pi `PUT`s; we cannot change that website
- **Optional:** tiny preview page on the Pi for staff/LAN testing (`pi/static/`) — not the public site

## Ranking

1. Higher `score` wins  
2. Tie → lower `time_used_seconds` wins (faster)

Same team name again: **keep best** by default (all submissions logged). See [docs/api.md](docs/api.md).

Public rows never include `counted_answers` / `attempts` (answer keys stay on the Pi only).

**Persistence:** every submission and the current leaderboard are written to SQLite on disk at `pi/data/scoreboard.db`. A Pi reboot keeps the board; use `POST /api/v1/admin/reset` to clear an event.

## Quick start (local)

```bash
cd pi
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy config.example.env config.env   # or: cp config.example.env config.env
```

Edit `pi/config.env` for saintcon push (optional until you have credentials):

```env
SCOREBOARD_PUSH_URL=
SCOREBOARD_PUSH_TOKEN=
```

**Auth:** there is no separate API secret. The bearer token **is the Pi’s IP address** — the same IP stations put in the URL.

Run:

```bash
python run.py
```

- Health: http://127.0.0.1:8080/health  
- API docs: http://127.0.0.1:8080/docs  
- Optional staff preview: http://127.0.0.1:8080/ (not saintcon.org)

### Example: submit a fake Orbit run

Locally, use `127.0.0.1` as both the host and the bearer token:

```bash
curl.exe -X POST http://127.0.0.1:8080/api/v1/runs ^
  -H "Authorization: Bearer 127.0.0.1" ^
  -H "Content-Type: application/json" ^
  --data-binary @examples/orbit-run.json
```

On the event LAN, if the Pi is `192.168.1.50`:

```bash
curl -X POST http://192.168.1.50:8080/api/v1/runs \
  -H "Authorization: Bearer 192.168.1.50" \
  -H "Content-Type: application/json" \
  --data-binary @examples/orbit-run.json
```

Then `GET /api/v1/leaderboard` (or the optional preview page) should show **Orbit** at rank 1 with score `42.5`. With push URL/token set, the same ranking is PUTed to saintcon.org.

### Reset event

```bash
curl.exe -X POST http://127.0.0.1:8080/api/v1/admin/reset ^
  -H "Authorization: Bearer 127.0.0.1"
```

## Game PC contract (other repo)

When a station writes `results/<team_slug>/<UTC_timestamp>/summary.json`, POST that object wrapped in an envelope:

```json
{
  "machine_id": "station-3",
  "submitted_at": "2026-10-19T21:12:35Z",
  "summary": { "...contents of summary.json..." }
}
```

to `POST http://<pi-ip>:8080/api/v1/runs` with `Authorization: Bearer <pi-ip>` (token = Pi IP). Field definitions: [schema/summary.schema.json](schema/summary.schema.json) and [docs/api.md](docs/api.md).

## saintcon.org push (the only public website path)

Their API (unchanged by us — we only call it):

```bash
curl -X PUT https://saintcon.org/api/scoreboards/<id> \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d @board.json
```

Each PUT **replaces the whole board**. Fields we can send: `status`, `frozen`, `updated_at`, `message`, and `entries[]` with `rank`, `name`, `score`, optional `detail` / `team`. Limits: ≤200 entries, ≥15s between pushes, body ≤64 KB.

Configure on the Pi:

```env
SCOREBOARD_PUSH_URL=https://saintcon.org/api/scoreboards/<id>
SCOREBOARD_PUSH_TOKEN=<key>
```

On each score change the aggregator builds ranked `entries` (`name` = team, `score`, `detail` = roster names only — game length is standardized so time used is not shown) and PUTs, debounced to ≥15 seconds.

## Layout

```
/
  README.md
  docs/
    api.md
    deployment-pi.md
  schema/
    summary.schema.json
  examples/
    orbit-run.json
  pi/
    app/           # FastAPI aggregator + saintcon PUT client
    static/        # optional staff preview only (not the public site)
    requirements.txt
    config.example.env
    run.py
  docker-compose.yml
```

There is **no** `web/` public frontend here — saintcon.org owns that.

## Deploy on a Pi

See [docs/deployment-pi.md](docs/deployment-pi.md). Short version: venv + `python run.py`, systemd unit, point game PCs at the Pi IP, set saintcon push env vars. Public TVs should show **saintcon.org**; the Pi URL is only for staff/debug if you want it.

## Out of scope

- Changing or hosting the saintcon.org scoreboard UI  
- Game UI, baton/serial, questions, challenges, WSL  
- Patching the Windows game to POST (document the API; implement in the game repo next)
