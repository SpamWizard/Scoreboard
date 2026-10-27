from __future__ import annotations

import hashlib
from typing import Any


def make_run_id(machine_id: str, team: str, finished_at: str, ts: str) -> str:
    """Stable id for idempotent upserts of the same finished run."""
    material = f"{machine_id}|{team}|{finished_at}|{ts}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def is_better_run(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
    """
    Ranking rule (also used for keep-best team policy):
      1. Higher score wins
      2. If score tied, lower time_used_seconds wins (faster)
    """
    c_score = float(candidate["score"])
    i_score = float(incumbent["score"])
    if c_score != i_score:
        return c_score > i_score
    return float(candidate["time_used_seconds"]) < float(incumbent["time_used_seconds"])


def sort_key(row: dict[str, Any]) -> tuple[float, float]:
    """Sort key for leaderboard: score desc, time_used_seconds asc."""
    return (-float(row["score"]), float(row["time_used_seconds"]))


def public_view(summary: dict[str, Any]) -> dict[str, Any]:
    """Slim fields safe for public display (no answer keys / attempts)."""
    roster = summary.get("roster") or []
    players = summary.get("players") or []
    return {
        "team": summary.get("team"),
        "score": summary.get("score"),
        "time_used": summary.get("time_used"),
        "time_used_seconds": summary.get("time_used_seconds"),
        "finished_at": summary.get("finished_at"),
        "started_at": summary.get("started_at"),
        "reason": summary.get("reason"),
        "ts": summary.get("ts"),
        "roster_names": [p.get("name", "") for p in roster if isinstance(p, dict)],
        "players": [
            {
                "player_number": p.get("player_number"),
                "name": p.get("name"),
                "points": p.get("points"),
            }
            for p in players
            if isinstance(p, dict)
        ],
    }
