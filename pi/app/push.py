from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .db import utc_now_iso
from .settings import Settings

logger = logging.getLogger("scoreboard.push")


def _clip(value: str, limit: int) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


class SaintconPusher:
    """
    Pushes the full ranked board to saintcon.org via PUT.
    At most one successful push every min_interval seconds (API limit: 15s).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._last_push_mono: float = 0.0
        self._pending: bool = False
        self._debounce_task: asyncio.Task[None] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.push_url and self.settings.push_token)

    def schedule(self, entries: list[dict[str, Any]]) -> None:
        """Queue a push of the current leaderboard (debounced to respect rate limit)."""
        if not self.configured:
            return
        self._pending_payload = self._build_payload(entries)
        self._pending = True
        if self._debounce_task is None or self._debounce_task.done():
            self._debounce_task = asyncio.create_task(self._flush_when_ready())

    def _build_payload(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        board_entries: list[dict[str, Any]] = []
        for entry in entries[:200]:
            names = entry.get("roster_names") or []
            detail = ", ".join(str(n) for n in names if n)
            board_entries.append(
                {
                    "rank": int(entry["rank"]),
                    "name": _clip(str(entry["team"]), 40),
                    "score": float(entry["score"]),
                    "detail": _clip(
                        f"{entry.get('time_used', '')}"
                        + (f" · {detail}" if detail else ""),
                        60,
                    ),
                    "team": None,
                }
            )
        payload: dict[str, Any] = {
            "status": self.settings.push_status or "live",
            "frozen": False,
            "updated_at": utc_now_iso(),
            "entries": board_entries,
        }
        message = (self.settings.push_message or "").strip()
        if message:
            payload["message"] = _clip(message, 140)
        return payload

    async def _flush_when_ready(self) -> None:
        while self._pending:
            wait = self.settings.push_min_interval_seconds - (
                time.monotonic() - self._last_push_mono
            )
            if wait > 0:
                await asyncio.sleep(wait)
            async with self._lock:
                if not self._pending:
                    return
                payload = getattr(self, "_pending_payload", None)
                self._pending = False
                if payload is None:
                    return
                ok = await self._put(payload)
                if ok:
                    self._last_push_mono = time.monotonic()
                else:
                    # Retry after another interval on failure
                    self._pending = True
                    await asyncio.sleep(self.settings.push_min_interval_seconds)

    async def _put(self, payload: dict[str, Any]) -> bool:
        headers = {
            "Authorization": f"Bearer {self.settings.push_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.put(
                    self.settings.push_url, json=payload, headers=headers
                )
            if response.status_code >= 400:
                logger.warning(
                    "saintcon push failed: %s %s",
                    response.status_code,
                    response.text[:300],
                )
                return False
            logger.info(
                "saintcon push ok: %s entries, status=%s",
                len(payload.get("entries", [])),
                response.status_code,
            )
            return True
        except Exception:
            logger.exception("saintcon push error")
            return False

    async def push_now(self, entries: list[dict[str, Any]]) -> bool:
        """Immediate push (still respects in-flight lock; ignores debounce)."""
        if not self.configured:
            return False
        payload = self._build_payload(entries)
        async with self._lock:
            ok = await self._put(payload)
            if ok:
                self._last_push_mono = time.monotonic()
                self._pending = False
            return ok
