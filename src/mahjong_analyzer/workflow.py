from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import AnalyzerError
from .schema import connect, initialize
from .tenhou import (
    _existing_review,
    _mjai_conversion,
    _safe_stem,
    analyze_tenhou_path,
    convert_mjlog,
    inspect_mjlog,
    reviewer_version,
)
from .runner import AnalysisConfig


@dataclass(frozen=True)
class WorkflowResult:
    input_files: int
    detected_games: int
    analyzed_games: int
    skipped_duplicates: int
    failures: int
    held: int
    processed_moved: int
    failed_moved: int
    duplicate_removed: int
    new_games: int
    new_reviews: int
    new_decisions: int
    details: tuple[dict[str, object], ...]


def ensure_tenhou_directories(root: Path) -> tuple[Path, Path, Path]:
    inbox = root / "inbox"
    processed = root / "processed"
    failed = root / "failed"
    for directory in (inbox, processed, failed):
        directory.mkdir(parents=True, exist_ok=True)
    return inbox, processed, failed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replay_files(directory: Path) -> list[Path]:
    return sorted([*directory.glob("*.mjlog"), *directory.glob("*.xml.gz")])


def _db_counts(database: Path) -> tuple[int, int, int]:
    connection = connect(database)
    try:
        initialize(connection)
        return tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("games", "reviews", "decisions")
        )
    finally:
        connection.close()


def _successful_source_exists(
    database: Path,
    source_sha256: str,
    *,
    player_id: int,
    reviewer_version_value: str,
    temperature: float,
    model_tag: str,
) -> bool:
    connection = connect(database)
    try:
        initialize(connection)
        row = connection.execute(
            """
            SELECT 1 FROM games g JOIN reviews r ON r.game_id = g.id
            WHERE g.source_sha256 = ? AND r.player_id = ?
              AND lower(r.engine) = 'mortal'
              AND r.reviewer_version = ? AND r.temperature = ?
              AND r.model_tag = ?
            LIMIT 1
            """,
            (source_sha256, player_id, reviewer_version_value, temperature, model_tag),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _processed_copy(processed: Path, source_sha256: str) -> Path | None:
    for candidate in _replay_files(processed):
        try:
            if _sha256(candidate) == source_sha256:
                return candidate
        except OSError:
            continue
    return None


def _destination(directory: Path, source: Path, source_sha256: str) -> Path:
    candidate = directory / source.name
    if not candidate.exists():
        return candidate
    if _sha256(candidate) == source_sha256:
        return candidate
    suffix = source.suffix
    stem = source.name[:-len(suffix)] if suffix else source.name
    return directory / f"{stem}.{source_sha256[:12]}{suffix}"


def _copy_then_remove(source: Path, destination: Path, source_sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.absolute() == destination.absolute():
        if _sha256(source) != source_sha256:
            raise AnalyzerError("source SHA-256 changed before file organization")
        return destination
    if destination.exists():
        if _sha256(destination) != source_sha256:
            raise AnalyzerError(f"destination collision with different content: {destination}")
        source.unlink()
        return destination
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        shutil.copy2(source, temporary)
        if _sha256(temporary) != source_sha256:
            raise AnalyzerError("source and destination SHA-256 differ after copy")
        temporary.rename(destination)
        if _sha256(destination) != source_sha256:
            raise AnalyzerError("destination SHA-256 verification failed")
        source.unlink()
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_failure_log(path: Path, *, source_sha256: str, reason: str) -> None:
    log_path = path.with_name(f"{path.name}.error.json")
    log_path.write_text(
        json.dumps(
            {"source": path.name, "source_sha256": source_sha256,
             "reason": reason, "recorded_at": time.time()},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def _backfill_source_hash(
    database: Path,
    *,
    log_sha256: str,
    source_sha256: str,
    player_id: int,
    reviewer_version_value: str,
    temperature: float,
    model_tag: str,
) -> bool:
    connection = connect(database)
    try:
        initialize(connection)
        rows = connection.execute(
            """
            SELECT g.id FROM games g JOIN reviews r ON r.game_id = g.id
            WHERE g.log_sha256 = ? AND g.source_sha256 IS NULL
              AND r.player_id = ? AND lower(r.engine) = 'mortal'
              AND r.reviewer_version = ? AND r.temperature = ? AND r.model_tag = ?
            """,
            (log_sha256, player_id, reviewer_version_value, temperature, model_tag),
        ).fetchall()
        if len(rows) != 1:
            return False
        connection.execute("UPDATE games SET source_sha256 = ? WHERE id = ?", (source_sha256, rows[0]["id"]))
        connection.commit()
        return True
    finally:
        connection.close()


def _preflight_registered(
    path: Path,
    database: Path,
    *,
    player_id: int,
    converter_executable: Path,
    reviewer_executable: Path,
    output_dir: Path,
    model_tag: str,
    temperature: float,
    timeout: int,
) -> tuple[bool, str, str]:
    metadata = inspect_mjlog(path)
    normalized = convert_mjlog(metadata, converter_executable, output_dir, timeout=timeout)
    _, log_sha = _mjai_conversion(
        reviewer_executable, normalized, player_id, output_dir / "preflight", timeout=timeout,
    )
    version = reviewer_version(reviewer_executable, timeout=timeout)
    connection = connect(database)
    try:
        initialize(connection)
        registered = _existing_review(
            connection, game_id=metadata.game_id, log_sha256=log_sha,
            source_sha256=metadata.source_sha256, player_id=player_id,
            reviewer_version_value=version, temperature=temperature, model_tag=model_tag,
        )
    finally:
        connection.close()
    if registered:
        backfilled = _backfill_source_hash(
            database, log_sha256=log_sha, source_sha256=metadata.source_sha256,
            player_id=player_id, reviewer_version_value=version,
            temperature=temperature, model_tag=model_tag,
        )
        if not backfilled and not _successful_source_exists(
            database, metadata.source_sha256, player_id=player_id,
            reviewer_version_value=version, temperature=temperature, model_tag=model_tag,
        ):
            registered = False
    return registered, metadata.source_sha256, log_sha


def migrate_existing_tenhou(
    source: Path,
    root: Path,
    database: Path,
    *,
    player_id: int,
    converter_executable: Path,
    reviewer_executable: Path,
    output_dir: Path,
    model_tag: str,
    temperature: float,
    timeout: int,
) -> dict[str, object]:
    """Move an already-reviewed local replay without starting Mortal."""
    _, processed, _ = ensure_tenhou_directories(root)
    source_sha = _sha256(source)
    registered, _, _ = _preflight_registered(
        source, database, player_id=player_id, converter_executable=converter_executable,
        reviewer_executable=reviewer_executable, output_dir=output_dir, model_tag=model_tag,
        temperature=temperature, timeout=timeout,
    )
    if not registered:
        return {"status": "held", "path": str(source), "reason": "no matching successful review"}
    destination = _destination(processed, source, source_sha)
    _copy_then_remove(source, destination, source_sha)
    return {"status": "migrated", "path": str(destination), "source_sha256": source_sha}


def organize_tenhou_inbox(
    root: Path,
    database: Path,
    *,
    player_id: int,
    converter_executable: Path,
    analysis_config: AnalysisConfig,
    model_tag: str,
    output_dir: Path,
    retry_failed: bool = False,
    timeout: int = 1800,
) -> WorkflowResult:
    inbox, processed, failed = ensure_tenhou_directories(root)
    paths = _replay_files(inbox)
    if retry_failed:
        paths.extend(_replay_files(failed))
    details: list[dict[str, object]] = []
    counts = {"detected": 0, "analyzed": 0, "skipped": 0, "failures": 0,
              "held": 0, "processed": 0, "failed_moved": 0, "duplicate_removed": 0,
              "new_games": 0, "new_reviews": 0, "new_decisions": 0}
    version = reviewer_version(analysis_config.reviewer_executable, timeout=timeout)
    for path in paths:
        try:
            source_sha = _sha256(path)
            existing = _processed_copy(processed, source_sha)
            if existing and _successful_source_exists(
                database, source_sha, player_id=player_id, reviewer_version_value=version,
                temperature=analysis_config.temperature, model_tag=model_tag,
            ):
                path.unlink()
                counts["skipped"] += 1
                counts["duplicate_removed"] += 1
                details.append({"path": str(path), "status": "duplicate_file", "processed": str(existing)})
                continue
            before = _db_counts(database)
            result = analyze_tenhou_path(
                path, database, player_id, converter_executable=converter_executable,
                analysis_config=analysis_config, output_dir=output_dir, model_tag=model_tag,
                timeout=timeout,
            )
            if result.detected_games:
                counts["detected"] += result.detected_games
            if result.analyzed_games:
                counts["analyzed"] += result.analyzed_games
            if result.skipped_duplicates:
                counts["skipped"] += result.skipped_duplicates
            if result.failures:
                raise AnalyzerError("; ".join(result.errors) or "Tenhou analysis failed")
            after = _db_counts(database)
            counts["new_games"] += max(0, after[0] - before[0])
            counts["new_reviews"] += max(0, after[1] - before[1])
            counts["new_decisions"] += max(0, after[2] - before[2])
            destination = _destination(processed, path, source_sha)
            _copy_then_remove(path, destination, source_sha)
            counts["processed"] += 1
            details.append({"path": str(path), "status": "analyzed" if result.analyzed_games else "duplicate",
                            "processed": str(destination), "errors": list(result.errors)})
        except Exception as exc:  # keep processing independent inbox files
            counts["failures"] += 1
            source_sha = _sha256(path) if path.exists() else "unknown"
            try:
                destination = _destination(failed, path, source_sha)
                _copy_then_remove(path, destination, source_sha)
                _write_failure_log(destination, source_sha256=source_sha, reason=str(exc))
                counts["failed_moved"] += 1
                details.append({"path": str(path), "status": "failed", "failed": str(destination), "error": str(exc)})
            except Exception as move_exc:
                counts["held"] += 1
                details.append({"path": str(path), "status": "held", "error": str(exc),
                                "move_error": str(move_exc)})
    return WorkflowResult(
        input_files=len(paths), detected_games=counts["detected"], analyzed_games=counts["analyzed"],
        skipped_duplicates=counts["skipped"], failures=counts["failures"], held=counts["held"],
        processed_moved=counts["processed"], failed_moved=counts["failed_moved"],
        duplicate_removed=counts["duplicate_removed"], new_games=counts["new_games"],
        new_reviews=counts["new_reviews"], new_decisions=counts["new_decisions"],
        details=tuple(details),
    )
