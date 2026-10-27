from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .ranking import is_better_run, public_view, sort_key


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    team TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    score REAL NOT NULL,
                    time_used_seconds REAL NOT NULL,
                    summary_json TEXT NOT NULL,
                    UNIQUE(run_id)
                );

                CREATE TABLE IF NOT EXISTS team_best (
                    team TEXT PRIMARY KEY COLLATE NOCASE,
                    run_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    time_used_seconds REAL NOT NULL,
                    time_used TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    public_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_submissions_team
                    ON submissions(team COLLATE NOCASE);
                """
            )

    def upsert_run(
        self,
        *,
        run_id: str,
        machine_id: str,
        submitted_at: str,
        summary: dict[str, Any],
        policy: str,
    ) -> dict[str, Any]:
        """
        Store the submission and update the displayed team row.

        Returns:
          {
            "run_id": str,
            "team": str,
            "kept": bool,   # True if this run is now (or remains) the displayed best
            "duplicate": bool,
          }
        """
        team = summary["team"]
        score = float(summary["score"])
        time_used_seconds = float(summary["time_used_seconds"])
        received_at = utc_now_iso()
        summary_json = json.dumps(summary, ensure_ascii=False)
        public = public_view(summary)

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM submissions WHERE run_id = ?", (run_id,)
            ).fetchone()
            duplicate = existing is not None

            if not duplicate:
                conn.execute(
                    """
                    INSERT INTO submissions (
                        run_id, machine_id, team, submitted_at, received_at,
                        score, time_used_seconds, summary_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        machine_id,
                        team,
                        submitted_at,
                        received_at,
                        score,
                        time_used_seconds,
                        summary_json,
                    ),
                )

            incumbent = conn.execute(
                "SELECT * FROM team_best WHERE team = ? COLLATE NOCASE", (team,)
            ).fetchone()

            candidate = {
                "score": score,
                "time_used_seconds": time_used_seconds,
            }

            if incumbent is None:
                self._write_team_best(
                    conn,
                    team=team,
                    run_id=run_id,
                    machine_id=machine_id,
                    summary=summary,
                    public=public,
                    updated_at=received_at,
                )
                kept = True
            elif policy == "replace":
                self._write_team_best(
                    conn,
                    team=team,
                    run_id=run_id,
                    machine_id=machine_id,
                    summary=summary,
                    public=public,
                    updated_at=received_at,
                )
                kept = True
            else:
                # keep best
                if is_better_run(candidate, dict(incumbent)):
                    self._write_team_best(
                        conn,
                        team=team,
                        run_id=run_id,
                        machine_id=machine_id,
                        summary=summary,
                        public=public,
                        updated_at=received_at,
                    )
                    kept = True
                else:
                    kept = incumbent["run_id"] == run_id

            return {
                "run_id": run_id,
                "team": team,
                "kept": kept,
                "duplicate": duplicate,
            }

    def _write_team_best(
        self,
        conn: sqlite3.Connection,
        *,
        team: str,
        run_id: str,
        machine_id: str,
        summary: dict[str, Any],
        public: dict[str, Any],
        updated_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO team_best (
                team, run_id, machine_id, score, time_used_seconds, time_used,
                finished_at, reason, public_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team) DO UPDATE SET
                run_id = excluded.run_id,
                machine_id = excluded.machine_id,
                score = excluded.score,
                time_used_seconds = excluded.time_used_seconds,
                time_used = excluded.time_used,
                finished_at = excluded.finished_at,
                reason = excluded.reason,
                public_json = excluded.public_json,
                updated_at = excluded.updated_at
            """,
            (
                team,
                run_id,
                machine_id,
                float(summary["score"]),
                float(summary["time_used_seconds"]),
                summary.get("time_used", ""),
                summary.get("finished_at", ""),
                summary.get("reason", ""),
                json.dumps(public, ensure_ascii=False),
                updated_at,
            ),
        )

    def leaderboard_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM team_best").fetchall()

        entries: list[dict[str, Any]] = []
        for row in rows:
            public = json.loads(row["public_json"])
            entries.append(
                {
                    "run_id": row["run_id"],
                    "team": row["team"],
                    "score": row["score"],
                    "time_used": row["time_used"],
                    "time_used_seconds": row["time_used_seconds"],
                    "machine_id": row["machine_id"],
                    "finished_at": row["finished_at"],
                    "reason": row["reason"],
                    "roster_names": public.get("roster_names") or [],
                    "players": public.get("players") or [],
                    "updated_at": row["updated_at"],
                }
            )
        entries.sort(key=sort_key)
        for i, entry in enumerate(entries, start=1):
            entry["rank"] = i
        return entries

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            teams = conn.execute("SELECT COUNT(*) AS c FROM team_best").fetchone()["c"]
            submissions = conn.execute("SELECT COUNT(*) AS c FROM submissions").fetchone()[
                "c"
            ]
        return {"teams": teams, "submissions": submissions}

    def reset_event(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM team_best")
            conn.execute("DELETE FROM submissions")
