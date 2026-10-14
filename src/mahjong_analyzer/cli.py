from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .errors import AnalyzerError
from .identity import load_tenhou_identity
from .importer import ImportMetadata, import_file
from .report import format_summary, list_games, show_game, summary
from .runner import AnalysisConfig, analyze_log
from .schema import connect, initialize
from .tenhou import analyze_tenhou_path
from .workflow import migrate_existing_tenhou, organize_tenhou_inbox


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
    analyze = sub.add_parser("analyze-log", help="Review a local Tenhou/6 JSON and import it")
    analyze.add_argument("path", type=Path)
    analyze.add_argument("--player-id", type=int, required=True)
    analyze.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    analyze.add_argument("--reviewer-exe", type=Path, required=True)
    analyze.add_argument("--mortal-exe", type=Path, required=True)
    analyze.add_argument("--mortal-cfg", type=Path, required=True)
    analyze.add_argument("--output-dir", type=Path, default=Path("local_data/analysis"))
    analyze.add_argument("--temperature", type=float, default=0.1)
    analyze.add_argument("--timeout", type=int, default=900)
    analyze.add_argument("--python-path", type=Path)
    analyze.add_argument("--game-id")
    analyze.add_argument("--played-at")
    analyze.add_argument("--game-type")
    analyze.add_argument("--rule-context")
    tenhou = sub.add_parser("analyze-tenhou", help="Convert local Tenhou mjlog files, review, and import them")
    tenhou.add_argument("path", type=Path)
    tenhou.add_argument("--player-id", type=int)
    tenhou.add_argument("--config", type=Path, default=Path("local_data/config.json"))
    tenhou.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    tenhou.add_argument("--converter-exe", type=Path, required=True)
    tenhou.add_argument("--reviewer-exe", type=Path, required=True)
    tenhou.add_argument("--mortal-exe", type=Path, required=True)
    tenhou.add_argument("--mortal-cfg", type=Path, required=True)
    tenhou.add_argument("--model-tag", required=True)
    tenhou.add_argument("--output-dir", type=Path, default=Path("local_data/tenhou-analysis"))
    tenhou.add_argument("--temperature", type=float, default=0.1)
    tenhou.add_argument("--timeout", type=int, default=1800)
    tenhou.add_argument("--python-path", type=Path)
    tenhou.add_argument("--game-id")
    organize = sub.add_parser("organize-tenhou", help="Process the Tenhou inbox and organize source files")
    organize.add_argument("--root", type=Path, default=Path("data/raw/tenhou"))
    organize.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    organize.add_argument("--player-id", type=int)
    organize.add_argument("--config", type=Path, default=Path("local_data/config.json"))
    organize.add_argument("--converter-exe", type=Path, required=True)
    organize.add_argument("--reviewer-exe", type=Path, required=True)
    organize.add_argument("--mortal-exe", type=Path, required=True)
    organize.add_argument("--mortal-cfg", type=Path, required=True)
    organize.add_argument("--model-tag", required=True)
    organize.add_argument("--output-dir", type=Path, default=Path("local_data/tenhou-analysis"))
    organize.add_argument("--temperature", type=float, default=0.1)
    organize.add_argument("--timeout", type=int, default=1800)
    organize.add_argument("--python-path", type=Path)
    organize.add_argument("--retry-failed", action="store_true")
    organize.add_argument("--migrate-existing", type=Path, action="append", default=[])
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
    if args.command == "analyze-log":
        try:
            result = analyze_log(
                args.path,
                Path(args.database),
                args.player_id,
                AnalysisConfig(
                    reviewer_executable=args.reviewer_exe,
                    mortal_executable=args.mortal_exe,
                    mortal_config=args.mortal_cfg,
                    output_dir=args.output_dir,
                    temperature=args.temperature,
                    timeout_seconds=args.timeout,
                    python_path=args.python_path,
                ),
                game_id=args.game_id,
                played_at=args.played_at,
                game_type=args.game_type,
                rule_context=args.rule_context,
            )
            print(json.dumps({"status": result.import_status,
                              "mjai": str(result.mjai_path),
                              "review": str(result.review_path)}, ensure_ascii=False))
            with _db(args) as connection:
                print(format_summary(summary(connection, 0.05)))
            return 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "analyze-tenhou":
        try:
            identity_config = load_tenhou_identity(args.config) if args.config.exists() else None
            result = analyze_tenhou_path(
                args.path,
                Path(args.database),
                args.player_id,
                converter_executable=args.converter_exe,
                analysis_config=AnalysisConfig(
                    reviewer_executable=args.reviewer_exe,
                    mortal_executable=args.mortal_exe,
                    mortal_config=args.mortal_cfg,
                    output_dir=args.output_dir / "analysis",
                    temperature=args.temperature,
                    timeout_seconds=args.timeout,
                    python_path=args.python_path,
                ),
                output_dir=args.output_dir,
                model_tag=args.model_tag,
                game_id=args.game_id,
                timeout=args.timeout,
                identity_config=identity_config,
            )
            print(json.dumps({
                "input_files": result.input_files,
                "detected_games": result.detected_games,
                "analyzed_games": result.analyzed_games,
                "skipped_duplicates": result.skipped_duplicates,
                "failures": result.failures,
                "registered_decisions": result.registered_decisions,
                "errors": list(result.errors),
            }, ensure_ascii=False))
            return 1 if result.failures else 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "organize-tenhou":
        try:
            identity_config = load_tenhou_identity(args.config) if args.config.exists() else None
            config = AnalysisConfig(
                reviewer_executable=args.reviewer_exe,
                mortal_executable=args.mortal_exe,
                mortal_config=args.mortal_cfg,
                output_dir=args.output_dir / "analysis",
                temperature=args.temperature,
                timeout_seconds=args.timeout,
                python_path=args.python_path,
            )
            migrations = []
            for source in args.migrate_existing:
                migrations.append(migrate_existing_tenhou(
                    source, args.root, Path(args.database), player_id=args.player_id,
                    converter_executable=args.converter_exe,
                    reviewer_executable=args.reviewer_exe,
                    output_dir=args.output_dir, model_tag=args.model_tag,
                    temperature=args.temperature, timeout=args.timeout,
                    identity_config=identity_config,
                ))
            result = organize_tenhou_inbox(
                args.root, Path(args.database), player_id=args.player_id,
                converter_executable=args.converter_exe, analysis_config=config,
                model_tag=args.model_tag, output_dir=args.output_dir,
                retry_failed=args.retry_failed, timeout=args.timeout,
                identity_config=identity_config,
            )
            print(json.dumps({
                "input_files": result.input_files,
                "detected_games": result.detected_games,
                "analyzed_games": result.analyzed_games,
                "skipped_duplicates": result.skipped_duplicates,
                "failures": result.failures,
                "held": result.held,
                "processed_moved": result.processed_moved,
                "failed_moved": result.failed_moved,
                "duplicate_removed": result.duplicate_removed,
                "new_games": result.new_games,
                "new_reviews": result.new_reviews,
                "new_decisions": result.new_decisions,
                "db_registered_games": result.new_games,
                "db_registered_reviews": result.new_reviews,
                "db_registered_decisions": result.new_decisions,
                "duplicate_files": result.duplicate_removed,
                "migrations": migrations,
                "details": list(result.details),
            }, ensure_ascii=False))
            return 1 if result.failures or result.held else 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    return 2
