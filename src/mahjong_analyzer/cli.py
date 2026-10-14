from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .analytics import (
    DIMENSIONS,
    SCORE_TARGETS,
    ContextFilters,
    aggregate_contexts,
    parse_score_bins,
    search_decisions,
)
from .errors import AnalyzerError
from .context import extract_contexts_path
from .identity import load_tenhou_identity
from .importer import ImportMetadata, import_file
from .report import format_summary, list_games, show_game, summary
from .review import get_review_scene
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


def _add_context_filter_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--extractor-version", default="phase2-context-v1")
    parser.add_argument("--turn-min", type=int)
    parser.add_argument("--turn-max", type=int)
    parser.add_argument("--turn-phase", choices=("early", "mid", "late", "unknown"))
    parser.add_argument("--shanten", type=int)
    parser.add_argument("--shanten-group", choices=("tenpai", "one", "two", "three_plus", "negative", "unknown"))
    parser.add_argument("--riichi-count", type=int)
    parser.add_argument("--riichi-min", type=int)
    parser.add_argument("--riichi-max", type=int)
    parser.add_argument("--rank", choices=("1", "2", "3", "4", "unknown"))
    parser.add_argument("--filter-score-target", choices=SCORE_TARGETS)
    parser.add_argument("--score-min", type=int)
    parser.add_argument("--score-max", type=int)
    parser.add_argument("--action-category")
    parser.add_argument("--bakaze")
    parser.add_argument("--kyoku", type=int)
    parser.add_argument("--honba", type=int)
    parser.add_argument("--dealer", choices=("yes", "no"))
    parser.add_argument("--model-tag")
    parser.add_argument("--reviewer-version")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--is-equal", choices=("yes", "no"))
    parser.add_argument("--probability-min", type=float)
    parser.add_argument("--probability-max", type=float)


def _context_filters(args: argparse.Namespace) -> ContextFilters:
    rank = None if args.rank in (None, "unknown") else int(args.rank)
    return ContextFilters(
        extractor_version=args.extractor_version,
        turn_min=args.turn_min, turn_max=args.turn_max, turn_phase=args.turn_phase,
        shanten=args.shanten, shanten_group=args.shanten_group,
        riichi_count=args.riichi_count, riichi_min=args.riichi_min, riichi_max=args.riichi_max,
        rank=rank, rank_unknown=args.rank == "unknown",
        score_target=args.filter_score_target, score_min=args.score_min, score_max=args.score_max,
        action_category=args.action_category, bakaze=args.bakaze, kyoku=args.kyoku, honba=args.honba,
        is_dealer=None if args.dealer is None else args.dealer == "yes",
        model_tag=args.model_tag, reviewer_version=args.reviewer_version,
        temperature=args.temperature,
        is_equal=None if args.is_equal is None else args.is_equal == "yes",
        probability_min=args.probability_min, probability_max=args.probability_max,
    )


def _print_context_result(value: object, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if isinstance(value, dict) and "items" in value:
        print(f"total={value['total']} offset={value['offset']} limit={value['limit']}")
        for item in value["items"]:
            print(f"decision_id={item['decision_id']} round={item['round_index']} "
                  f"event={item['source_event_index']} action={item['action_category']} "
                  f"prob={item['actual_probability']} equal={item['is_equal']}")
        return
    for item in value:
        print(f"group={item['group']} decisions={item['decision_count']} "
              f"games={item['game_count']} agreement={item['ai_agreement_rate']} "
              f"low_probability={item['low_recommendation_rate']}")


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
    contexts = sub.add_parser("extract-contexts", help="Extract decision contexts from saved review JSON files")
    contexts.add_argument("path", type=Path)
    contexts.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    contexts.add_argument("--extractor-version", default="phase2-context-v1")
    analyze_contexts = sub.add_parser("analyze-contexts", help="Aggregate saved decision contexts")
    analyze_contexts.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    analyze_contexts.add_argument("--dimension", choices=DIMENSIONS, default="all")
    analyze_contexts.add_argument("--score-diff-target", choices=SCORE_TARGETS)
    analyze_contexts.add_argument("--score-bins", default="0,4000,8000,12000")
    analyze_contexts.add_argument("--early-end", type=int, default=6)
    analyze_contexts.add_argument("--mid-end", type=int, default=12)
    analyze_contexts.add_argument("--format", choices=("json", "text"), default="json")
    _add_context_filter_options(analyze_contexts)
    search = sub.add_parser("search-decisions", help="Search saved decision contexts")
    search.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--early-end", type=int, default=6)
    search.add_argument("--mid-end", type=int, default=12)
    search.add_argument("--format", choices=("json", "text"), default="json")
    _add_context_filter_options(search)
    scene = sub.add_parser("show-decision", help="Show one review scene using saved context and MJAI")
    scene.add_argument("--database", default="local_data/mahjong_analyzer.sqlite3")
    scene.add_argument("--decision-id", type=int, required=True)
    scene.add_argument("--review-root", type=Path, default=Path("local_data"))
    scene.add_argument("--review-json", type=Path)
    scene.add_argument("--source-root", type=Path, default=Path("data/raw/tenhou"))
    scene.add_argument("--format", choices=("json", "text"), default="json")
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
    if args.command == "extract-contexts":
        try:
            connection = _db(args)
            try:
                results = extract_contexts_path(
                    connection, args.path, extractor_version=args.extractor_version,
                )
            finally:
                connection.close()
            print(json.dumps({
                "reviews": len(results),
                "total": sum(item.total for item in results),
                "complete": sum(item.complete for item in results),
                "event_mapped": sum(item.event_mapped for item in results),
                "non_action_mapped": sum(item.non_action_mapped for item in results),
                "partial": sum(item.partial for item in results),
                "unmapped": sum(item.unmapped for item in results),
                "shanten_success": sum(item.shanten_success for item in results),
                "turn_success": sum(item.turn_success for item in results),
                "score_success": sum(item.score_success for item in results),
                "inserted": sum(item.inserted for item in results),
                "duplicates": sum(item.duplicate for item in results),
            }, ensure_ascii=False))
            return 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "analyze-contexts":
        try:
            filters = _context_filters(args)
            score_bins = parse_score_bins(args.score_bins)
            # Analytics is intentionally read-only: do not run initialize(), which may
            # write schema metadata to an otherwise existing production database.
            with connect(Path(args.database)) as connection:
                result = aggregate_contexts(
                    connection, dimension=args.dimension, filters=filters,
                    early_end=args.early_end, mid_end=args.mid_end,
                    score_target=args.score_diff_target, score_bins=score_bins,
                )
            _print_context_result(result, args.format)
            return 0
        except (AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "search-decisions":
        try:
            filters = _context_filters(args)
            with connect(Path(args.database)) as connection:
                result = search_decisions(
                    connection, filters, offset=args.offset, limit=args.limit,
                    early_end=args.early_end, mid_end=args.mid_end,
                )
            _print_context_result({"total": result.total, "offset": result.offset,
                                   "limit": result.limit, "items": list(result.items)}, args.format)
            return 0
        except (AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "show-decision":
        try:
            with connect(Path(args.database)) as connection:
                result = get_review_scene(
                    connection, args.decision_id, review_root=args.review_root,
                    review_json=args.review_json, source_root=args.source_root,
                )
            if args.format == "json":
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                identity = result["identity"]
                mortal = result["mortal"]
                print(f"decision_id={identity['decision_id']} status={result['status']} "
                      f"round={identity['round_index']} event={identity['source_event_index']}")
                print(f"action={mortal['action_category']} equal={mortal['is_equal']} "
                      f"probability={mortal['actual_probability']}")
            return 0
        except (OSError, AnalyzerError, ValueError) as exc:
            print(f"error: {exc}")
            return 1
    return 2
