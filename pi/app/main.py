from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_admin_token, require_api_token
from .db import Database, utc_now_iso
from .models import (
    HealthResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    PublicPlayer,
    RunAccepted,
    RunSubmission,
)
from .netinfo import local_ipv4_addresses, primary_ipv4
from .push import SaintconPusher
from .ranking import make_run_id
from .settings import Settings, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scoreboard")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Terminal Relay Scoreboard",
    description="Pi aggregator: game PCs POST finished runs; Pi ranks and pushes to saintcon.org.",
    version="1.0.0",
)

# Simple in-memory rate limit for POSTs (per client IP)
_RATE_WINDOW_SECONDS = 60.0
_RATE_MAX_POSTS = 30
_rate_hits: dict[str, list[float]] = defaultdict(list)


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Database:
    return Database(settings.resolve_db_path())


def get_pusher(settings: Annotated[Settings, Depends(get_settings)]) -> SaintconPusher:
    # One pusher instance on the app state
    pusher = getattr(app.state, "pusher", None)
    if pusher is None:
        pusher = SaintconPusher(settings)
        app.state.pusher = pusher
    return pusher


@app.on_event("startup")
def on_startup() -> None:
    settings = get_settings()
    db = Database(settings.resolve_db_path())
    app.state.db = db
    app.state.pusher = SaintconPusher(settings)
    ips = ", ".join(sorted(local_ipv4_addresses()))
    logger.info(
        "scoreboard ready db=%s push=%s api_key=Pi_IP (%s) primary=%s",
        settings.resolve_db_path(),
        "on" if app.state.pusher.configured else "off",
        ips,
        primary_ipv4(),
    )


def _check_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _rate_hits[client]
    _rate_hits[client] = [t for t in window if now - t < _RATE_WINDOW_SECONDS]
    if len(_rate_hits[client]) >= _RATE_MAX_POSTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    _rate_hits[client].append(now)


def build_leaderboard(db: Database) -> LeaderboardResponse:
    rows = db.leaderboard_rows()
    entries = [
        LeaderboardEntry(
            rank=row["rank"],
            team=row["team"],
            score=row["score"],
            time_used=row["time_used"],
            time_used_seconds=row["time_used_seconds"],
            machine_id=row["machine_id"],
            finished_at=row["finished_at"],
            reason=row["reason"],
            roster_names=list(row["roster_names"]),
            players=[
                PublicPlayer(
                    player_number=int(p.get("player_number") or 0),
                    name=str(p.get("name") or ""),
                    points=float(p.get("points") or 0),
                )
                for p in row["players"]
            ],
            run_id=row["run_id"],
        )
        for row in rows
    ]
    return LeaderboardResponse(updated_at=utc_now_iso(), entries=entries)


@app.get("/health", response_model=HealthResponse)
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_db)],
) -> HealthResponse:
    stats = db.stats()
    return HealthResponse(
        status="ok",
        teams=stats["teams"],
        submissions=stats["submissions"],
        push_configured=bool(settings.push_url and settings.push_token),
    )


@app.get("/api/v1/leaderboard", response_model=LeaderboardResponse)
def leaderboard(db: Annotated[Database, Depends(get_db)]) -> LeaderboardResponse:
    """Public slim leaderboard (no auth). Safe for a LAN TV / local display."""
    return build_leaderboard(db)


@app.post("/api/v1/runs", response_model=RunAccepted)
def post_run(
    body: RunSubmission,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_db)],
    pusher: Annotated[SaintconPusher, Depends(get_pusher)],
    authorization: Annotated[str | None, Header()] = None,
) -> RunAccepted:
    require_api_token(authorization)
    _check_rate_limit(request)

    summary = body.summary.model_dump(mode="json")
    run_id = make_run_id(
        body.machine_id,
        summary["team"],
        summary["finished_at"],
        summary["ts"],
    )
    result = db.upsert_run(
        run_id=run_id,
        machine_id=body.machine_id,
        submitted_at=body.submitted_at,
        summary=summary,
        policy=settings.team_policy,
    )
    board = build_leaderboard(db)
    pusher.schedule([e.model_dump() for e in board.entries])

    logger.info(
        "run accepted team=%s machine=%s kept=%s duplicate=%s score=%s",
        result["team"],
        body.machine_id,
        result["kept"],
        result["duplicate"],
        summary["score"],
    )
    return RunAccepted(
        run_id=result["run_id"],
        team=result["team"],
        kept=result["kept"],
        policy=settings.team_policy,
        leaderboard=board,
    )


@app.post("/api/v1/admin/reset")
def reset_event(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_db)],
    pusher: Annotated[SaintconPusher, Depends(get_pusher)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Clear all submissions and the leaderboard. Staff only."""
    require_admin_token(authorization)
    db.reset_event()
    board = build_leaderboard(db)
    pusher.schedule([e.model_dump() for e in board.entries])
    logger.warning("event leaderboard reset")
    return {"ok": True, "leaderboard": board.model_dump()}


@app.post("/api/v1/admin/push")
async def force_push(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Database, Depends(get_db)],
    pusher: Annotated[SaintconPusher, Depends(get_pusher)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Force an immediate push to saintcon.org (still subject to their rate limit)."""
    require_admin_token(authorization)
    if not pusher.configured:
        raise HTTPException(status_code=400, detail="Push URL/token not configured")
    board = build_leaderboard(db)
    ok = await pusher.push_now([e.model_dump() for e in board.entries])
    return {"ok": ok, "entries": len(board.entries)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
