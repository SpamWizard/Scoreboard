"""CLI: scoreboard push <folder>"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .push import load_from_target, push_board


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def cmd_push(args: argparse.Namespace) -> int:
    try:
        board, source = load_from_target(args.target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(board, indent=2, ensure_ascii=False))
        return 0

    url = (args.url or _env("SAINTCON_SCOREBOARD_URL")).strip()
    token = (args.token or _env("SAINTCON_SCOREBOARD_TOKEN")).strip()
    if not url or not token:
        print(
            "error: need --url/--token or SAINTCON_SCOREBOARD_URL / SAINTCON_SCOREBOARD_TOKEN",
            file=sys.stderr,
        )
        return 1

    try:
        raw = push_board(url, token, board)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    n = len(board.get("entries") or [])
    print(f"pushed {n} entries from {source}")
    if raw.strip():
        print(raw[:500])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scoreboard",
        description="Push a scoreboard to saintcon.org",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    push_p = sub.add_parser(
        "push",
        help="PUT a board built from a results folder (or board.json)",
    )
    push_p.add_argument(
        "target",
        help=(
            "folder of Terminal Relay results (summary.json), "
            "a folder with board.json, or a board.json file"
        ),
    )
    push_p.add_argument(
        "--url",
        default="",
        help="https://saintcon.org/api/scoreboards/<id>",
    )
    push_p.add_argument(
        "--token",
        default="",
        help="Bearer key from saintcon",
    )
    push_p.add_argument(
        "--dry-run",
        action="store_true",
        help="print payload without sending",
    )
    push_p.set_defaults(func=cmd_push)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
