from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .errors import AnalyzerError
from .importer import ImportMetadata, import_file
from .report import format_summary, list_games, show_game, summary
from .schema import connect, initialize


def _db(args: argparse.Namespace) -> sqlite3.Connection:
    connection = connect(Path(args.database))
    initialize(connection)
    return connection


def _metadata(args: argparse.Namespace) -> ImportMetadata:
    return ImportMetadata(source=args.source, game_id=args.game_id, player_id=args.player_id,
                          played_at=args.played_at, game_type=args.game_type,
                          rule_context=args.rule_context)


def _add_import_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    parser.add_argument("--source", default="review-json")
    parser.add_argument("--game-id")
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--played-at")
    parser.add_argument("--game-type")
    parser.add_argument("--rule-context")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mahjong-analyzer")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-db", help="Initialize a SQLite database")
    init.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    one = sub.add_parser("import-review", help="Import one Mortal review JSON")
    one.add_argument("path", type=Path)
    _add_import_options(one)
    many = sub.add_parser("import-reviews", help="Import review JSON files from a directory")
    many.add_argument("path", type=Path)
    _add_import_options(many)
    games = sub.add_parser("list-games", help="List imported games")
    games.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    show = sub.add_parser("show-game", help="Show one game and its reviews")
    show.add_argument("game_id", type=int)
    show.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    report = sub.add_parser("summary", help="Summarize imported reviews")
    report.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    report.add_argument("--threshold", type=float, default=0.05)
    return parser


def _import_one(connection: sqlite3.Connection, path: Path, args: argparse.Namespace) -> str:
    return import_file(connection, path, _metadata(args))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-db":
        with _db(args):
            pass
        print(f"Initialized {args.database}")
        return 0
    if args.command == "import-review":
        try:
            with _db(args) as connection:
                result = _import_one(connection, args.path, args)
            print(f"{result}: {args.path}")
            return 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "import-reviews":
        paths = sorted(args.path.glob("*.json")) if args.path.is_dir() else []
        counts = {"imported": 0, "duplicate": 0, "error": 0}
        with _db(args) as connection:
            for path in paths:
                try:
                    counts[_import_one(connection, path, args)] += 1
                except (OSError, AnalyzerError, ValueError) as exc:
                    counts["error"] += 1
                    print(f"error: {path}: {exc}")
        print(json.dumps({"files": len(paths), **counts}, ensure_ascii=False))
        return 1 if counts["error"] else 0
    if args.command == "list-games":
        with _db(args) as connection:
            for row in list_games(connection):
                print(json.dumps(dict(row), ensure_ascii=False))
        return 0
    if args.command == "show-game":
        with _db(args) as connection:
            result = show_game(connection, args.game_id)
        if result is None:
            print(f"error: game {args.game_id} not found")
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "summary":
        try:
            with _db(args) as connection:
                print(format_summary(summary(connection, args.threshold)))
            return 0
        except ValueError as exc:
            print(f"error: {exc}")
            return 1
    return 2
