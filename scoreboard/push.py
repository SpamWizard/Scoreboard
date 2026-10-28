"""Build / PUT a board payload to saintcon.org."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clip(value: str, limit: int) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _clean_path(raw: str | Path) -> Path:
    """Normalize a user path; strip accidental wrapping quotes."""
    text = str(raw).strip().strip('"').strip("'")
    return Path(text).expanduser()


def _is_better(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
    c_score = float(candidate["score"])
    i_score = float(incumbent["score"])
    if c_score != i_score:
        return c_score > i_score
    return float(candidate.get("time_used_seconds", 0)) < float(
        incumbent.get("time_used_seconds", 0)
    )


def _roster_detail(summary: dict[str, Any]) -> str:
    names: list[str] = []
    for player in summary.get("roster") or []:
        if isinstance(player, dict) and player.get("name"):
            names.append(str(player["name"]))
    if not names:
        for player in summary.get("players") or []:
            if isinstance(player, dict) and player.get("name"):
                names.append(str(player["name"]))
    return ", ".join(names)


def board_from_summaries(root: Path) -> dict[str, Any]:
    """Scan a results tree for summary.json files; keep best score per team."""
    best_by_team: dict[str, dict[str, Any]] = {}
    found = 0
    for path in root.rglob("summary.json"):
        if not path.is_file():
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(summary, dict):
            continue
        team = str(summary.get("team") or "").strip()
        if not team or "score" not in summary:
            continue
        found += 1
        row = {
            "team": team,
            "score": float(summary["score"]),
            "time_used_seconds": float(summary.get("time_used_seconds") or 0),
            "detail": _roster_detail(summary),
        }
        key = team.casefold()
        if key not in best_by_team or _is_better(row, best_by_team[key]):
            best_by_team[key] = row

    if not found:
        raise FileNotFoundError(
            f"no summary.json (and no board.json) under: {root}"
        )

    ranked = sorted(
        best_by_team.values(),
        key=lambda r: (-float(r["score"]), float(r["time_used_seconds"])),
    )[:200]

    entries: list[dict[str, Any]] = []
    for i, row in enumerate(ranked, start=1):
        entry: dict[str, Any] = {
            "rank": i,
            "name": _clip(str(row["team"]), 40),
            "score": float(row["score"]),
            "team": None,
        }
        detail = _clip(str(row.get("detail") or ""), 60)
        if detail:
            entry["detail"] = detail
        entries.append(entry)

    return {
        "status": "live",
        "frozen": False,
        "updated_at": utc_now(),
        "entries": entries,
    }


def load_board_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("board JSON must be an object")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("board JSON must include an entries array")
    if len(entries) > 200:
        raise ValueError("at most 200 entries allowed")
    data.setdefault("status", "live")
    data.setdefault("frozen", False)
    data.setdefault("updated_at", utc_now())
    return data


def load_from_target(target: str | Path) -> tuple[dict[str, Any], str]:
    """
    Load a saintcon board from:
      - a board.json file
      - a folder with board.json
      - a Terminal Relay results folder (summary.json tree)
    Returns (board, source_label).
    """
    path = _clean_path(target)
    if not path.exists():
        raise FileNotFoundError(f"not found: {path}")

    if path.is_file():
        return load_board_file(path), str(path)

    board_json = path / "board.json"
    if board_json.is_file():
        return load_board_file(board_json), str(board_json)

    return board_from_summaries(path), str(path)


def push_board(url: str, token: str, board: dict[str, Any]) -> str:
    body = json.dumps(board, ensure_ascii=False).encode("utf-8")
    if len(body) > 64 * 1024:
        raise ValueError(f"body is {len(body)} bytes; saintcon limit is 64 KB")
    # Cloudflare Error 1010 bans stock Python-urllib user agents.
    # saintcon expects this custom UA (not a fake browser string).
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "saintcon-scoreboard-push/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc
