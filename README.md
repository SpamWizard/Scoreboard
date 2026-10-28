# scoreboard

Terminal command that **PUTs** a full board to saintcon.org.  
Each push **replaces the whole board**. Stdlib only.

## Install

From this repo:

```bash
pip install -e .
```

That gives you the `scoreboard` command.

## Usage

Point at a **Terminal Relay results folder** (it finds every `summary.json`, keeps the best score per team, builds the saintcon board, and PUTs it):

```powershell
scoreboard push "C:\Users\spam\Documents\terminal relay results"
```

Use quotes when the path has spaces. Don’t leave an extra `"` at the end.

PowerShell credentials:

```powershell
$env:SAINTCON_SCOREBOARD_URL = "https://saintcon.org/api/scoreboards/<id>"
$env:SAINTCON_SCOREBOARD_TOKEN = "<key>"
scoreboard push "C:\Users\spam\Documents\terminal relay results"
```

Or inline:

```powershell
scoreboard push "C:\Users\spam\Documents\terminal relay results" `
  --url "https://saintcon.org/api/scoreboards/<id>" `
  --token "<key>"
```

Dry run (print JSON, don’t send):

```powershell
scoreboard push "C:\Users\spam\Documents\terminal relay results" --dry-run
```

You can also push a folder that already has `board.json`, or a `board.json` file path.

Without installing:

```powershell
python -m scoreboard push "C:\Users\spam\Documents\terminal relay results"
```

## board.json

```json
{
  "status": "live",
  "frozen": false,
  "updated_at": "2026-10-28T19:04:00Z",
  "message": "Terminal Relay",
  "entries": [
    { "rank": 1, "name": "Orbit", "score": 42.5, "detail": "Ada, Ben, Cid", "team": null },
    { "rank": 2, "name": "Probe", "score": 30.0 }
  ]
}
```

| Rule | Limit |
|------|--------|
| Entries | ≤ 200, send all in rank order |
| `name` | required, ≤ 40 |
| `score` | required number |
| `detail` / `team` | optional |
| `status` | `upcoming` \| `live` \| `ended` \| `final` |
| Rate | ≤ 1 push / 15 s |
| Body | ≤ 64 KB |

`updated_at` is filled automatically if missing. See `examples/board.json`.
