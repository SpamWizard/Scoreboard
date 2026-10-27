from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class RosterPlayer(BaseModel):
    player_number: int
    name: str
    person_index: int | None = None
    color: str | None = None

    model_config = {"extra": "allow"}


class PlayerPoints(BaseModel):
    player_number: int
    name: str
    points: float

    model_config = {"extra": "allow"}


class Summary(BaseModel):
    """Mirrors results/.../summary.json from the game PC."""

    ts: str
    team: str
    roster: list[RosterPlayer] = Field(default_factory=list)
    started_at: str
    finished_at: str
    reason: str
    score: float
    time_used: str
    time_used_seconds: float
    game_limit_seconds: float
    game_remaining: float
    leg_remaining: float
    players: list[PlayerPoints] = Field(default_factory=list)
    counted_answers: list[Any] = Field(default_factory=list)
    attempts: list[Any] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @field_validator("team")
    @classmethod
    def team_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("team must be non-empty")
        return cleaned


class RunSubmission(BaseModel):
    """Envelope POSTed by a game PC to the Pi."""

    machine_id: str = Field(min_length=1, max_length=128)
    submitted_at: str
    summary: Summary


class PublicPlayer(BaseModel):
    player_number: int
    name: str
    points: float


class LeaderboardEntry(BaseModel):
    rank: int
    team: str
    score: float
    time_used: str
    time_used_seconds: float
    machine_id: str
    finished_at: str
    reason: str
    roster_names: list[str]
    players: list[PublicPlayer]
    run_id: str


class LeaderboardResponse(BaseModel):
    updated_at: str
    ranking: str = "score desc, then time_used_seconds asc"
    entries: list[LeaderboardEntry]


class RunAccepted(BaseModel):
    ok: bool = True
    run_id: str
    team: str
    kept: bool
    policy: str
    leaderboard: LeaderboardResponse


class HealthResponse(BaseModel):
    status: str
    teams: int
    submissions: int
    push_configured: bool
