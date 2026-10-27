# API contract

This repo owns the **Pi aggregator API**. Game PCs in `Terminal-relay-software-in-the-big-26` / `baton_relay` will POST finished `summary.json` payloads here. The Pi then ranks teams and pushes a slim board to **saintcon.org**.

## Auth

All write endpoints require the **Pi’s IP address** as the bearer token (no separate secret):

```http
Authorization: Bearer <pi-ip>
```

Example: stations post to `http://192.168.1.50:8080` with `Authorization: Bearer 192.168.1.50`.

Any of the Pi’s local IPv4 addresses is accepted (including `127.0.0.1` for local testing). Admin reset/push uses the same key.

`GET /api/v1/leaderboard` and `GET /health` are unauthenticated (public slim view only).

## Ranking

1. Higher `score` wins.
2. If `score` is tied, lower `time_used_seconds` wins (faster finish).

When the same team name submits again (`SCOREBOARD_TEAM_POLICY=best`, default):

- All submissions are **logged**.
- The displayed row is the **best** run for that team name (event-wide unique teams).
- Set `SCOREBOARD_TEAM_POLICY=replace` to always show the newest submission instead.

Idempotent retries of the same finished run (same `machine_id` + `team` + `finished_at` + `ts`) upsert by a stable `run_id` and do not create duplicates.

## `POST /api/v1/runs`

Submit a finished run. Call this when `summary.json` is written on the game PC.

### Request

```http
POST /api/v1/runs
Authorization: Bearer <pi-ip>
Content-Type: application/json
```

```json
{
  "machine_id": "station-3",
  "submitted_at": "2026-10-19T21:12:35Z",
  "summary": { "...full summary.json object..." }
}
```

| Field | Required | Notes |
|--------|----------|--------|
| `machine_id` | yes | Stable id for the game PC (e.g. `station-3`) |
| `submitted_at` | yes | UTC ISO when the client POSTs |
| `summary` | yes | Exact contents of `summary.json` (see [schema](../schema/summary.schema.json)) |

### Response `200`

```json
{
  "ok": true,
  "run_id": "a1b2c3…",
  "team": "Orbit",
  "kept": true,
  "policy": "best",
  "leaderboard": { "updated_at": "…", "ranking": "…", "entries": [ … ] }
}
```

- `kept: true` — this run is (or remains) the displayed row for that team.
- `kept: false` — logged, but a better prior run for that team is still shown.
- Response includes a current leaderboard snapshot so the game client can optionally show placement.

### Errors

| Status | Meaning |
|--------|---------|
| `401` | Missing/invalid bearer token (must be the Pi IP) |
| `422` | Malformed body / missing required summary fields |
| `429` | Too many POSTs from this IP (~30 / minute) |

## `GET /api/v1/leaderboard`

Public ranked rows for the local big-screen page (and any display client). **Does not** include `counted_answers`, `attempts`, or answer keys.

Each entry:

| Field | Notes |
|--------|--------|
| `rank` | 1-based |
| `team` | Display name |
| `score` | Final score |
| `time_used` | e.g. `12:34` |
| `time_used_seconds` | Tie-break value |
| `machine_id` | Station that submitted the kept run |
| `finished_at` | From summary |
| `reason` | End reason |
| `roster_names` | Player names |
| `players` | `{player_number, name, points}` |
| `run_id` | Stable id |

## `GET /health`

```json
{ "status": "ok", "teams": 3, "submissions": 5, "push_configured": true }
```

## Staff admin

Same bearer auth as runs: `Authorization: Bearer <pi-ip>`.

### `POST /api/v1/admin/reset`

Clears all submissions and the leaderboard, then schedules a push of an empty board to saintcon.org.

### `POST /api/v1/admin/push`

Forces an immediate push of the current board to saintcon.org.

## Game PC follow-up (other repo)

After writing `summary.json`, approximately:

```python
# TOKEN is the Pi IP, same as in PI_BASE (e.g. "192.168.1.50")
requests.post(
    f"http://{PI_IP}:8080/api/v1/runs",
    headers={"Authorization": f"Bearer {PI_IP}"},
    json={
        "machine_id": MACHINE_ID,
        "submitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary_dict,
    },
    timeout=10,
)
```

## saintcon.org push (Pi → public site we do not control)

The attendee-facing website is **saintcon.org**. This repo does not host or restyle it — we only call their replace-board `PUT` API. Configured via `SCOREBOARD_PUSH_URL` + `SCOREBOARD_PUSH_TOKEN`. On leaderboard changes the Pi `PUT`s:

```http
PUT https://saintcon.org/api/scoreboards/<id>
Authorization: Bearer <key>
Content-Type: application/json
```

```json
{
  "status": "live",
  "frozen": false,
  "updated_at": "2026-10-28T19:04:00Z",
  "message": "optional staff note",
  "entries": [
    {
      "rank": 1,
      "name": "Orbit",
      "score": 42.5,
      "detail": "12:34 · Ada, Ben, Cid",
      "team": null
    }
  ]
}
```

Constraints (from saintcon): whole board replaced each PUT; ≤200 entries; `name` ≤40; `detail` ≤60; ≥15s between pushes; body ≤64 KB. The Pi debounces to respect the 15s minimum.
