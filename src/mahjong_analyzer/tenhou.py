from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .compat import normalize_tenhou6_payload
from .errors import AnalyzerError, ValidationError
from .identity import TenhouIdentityConfig, resolve_player_id
from .importer import _canonical
from .runner import AnalysisConfig, AnalysisResult, analyze_log
from .schema import connect, initialize


class TenhouImportError(AnalyzerError):
    """Raised when a local Tenhou mjlog cannot be safely imported."""


@dataclass(frozen=True)
class TenhouReplayMetadata:
    path: Path
    game_id: str
    source_sha256: str
    game_type: str
    rule_context: str
    round_count: int
    result_count: int
    player_names: tuple[str, ...]
    tw_player_id: int | None


@dataclass(frozen=True)
class TenhouBatchResult:
    input_files: int
    detected_games: int
    analyzed_games: int
    skipped_duplicates: int
    failures: int
    registered_decisions: int
    errors: tuple[str, ...]


_GAME_ID = re.compile(r"(?P<id>\d{10}gm-\d{4}-\d{4}-[0-9a-fA-F]+)")
_TW = re.compile(r"(?:^|[&_])tw(?:=)?(?P<value>[^&_.]+)")


def _read_xml(path: Path) -> tuple[bytes, ET.Element]:
    if not path.is_file():
        raise TenhouImportError(f"mjlog file does not exist: {path}")
    try:
        raw = path.read_bytes()
        xml = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        root = ET.fromstring(xml)
    except (OSError, EOFError, gzip.BadGzipFile, ET.ParseError) as exc:
        raise TenhouImportError("input must be a valid Tenhou mjlog XML or gzip XML") from exc
    if root.tag != "mjloggm":
        raise TenhouImportError("mjlog XML root must be mjloggm")
    return raw, root


def inspect_mjlog(path: Path, *, game_id: str | None = None) -> TenhouReplayMetadata:
    raw, root = _read_xml(path)
    rounds = root.findall("INIT")
    results = root.findall("AGARI") + root.findall("RYUUKYOKU")
    if len(root.findall("TAIKYOKU")) != 1 or not rounds or len(results) < len(rounds):
        raise TenhouImportError("mjlog must contain exactly one game with complete rounds")
    discovered = game_id or (_GAME_ID.search(path.name).group("id") if _GAME_ID.search(path.name) else None)
    if not discovered:
        raise TenhouImportError("Tenhou game ID is not present in the filename; provide --game-id")
    go = root.find("GO")
    go_type = int(go.attrib.get("type", "9")) if go is not None else 9
    game_type = "hanchan" if go_type & 0x08 else "tonpuu"
    rule_context = json.dumps(
        {"format": "mjlog", "version": root.attrib.get("ver"), "go_type": go_type},
        sort_keys=True,
        separators=(",", ":"),
    )
    un = root.find("UN")
    if un is None:
        raise TenhouImportError("mjlog does not contain player information")
    raw_names = [un.attrib.get(f"n{index}") for index in range(4)]
    if any(not isinstance(name, str) or not name for name in raw_names):
        raise TenhouImportError("mjlog does not contain four player names")
    player_names = tuple(unquote(name) for name in raw_names if name is not None)
    tw_match = _TW.search(path.name)
    tw_player_id: int | None = None
    if tw_match:
        value = tw_match.group("value")
        if value not in {"0", "1", "2", "3"}:
            raise ValidationError("filename tw view must be a seat number from 0 to 3")
        tw_player_id = int(value)
    return TenhouReplayMetadata(
        path=path,
        game_id=discovered,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        game_type=game_type,
        rule_context=rule_context,
        round_count=len(rounds),
        result_count=len(results),
        player_names=player_names,
        tw_player_id=tw_player_id,
    )


def _safe_stem(path: Path) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in path.stem)[:80] or "replay"


def _run(command: list[str], *, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command, check=False, shell=False, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TenhouImportError("local conversion process failed or timed out") from exc
    if completed.returncode != 0:
        raise TenhouImportError(f"local conversion process exited with status {completed.returncode}")
    return completed


def _require_executable(path: Path, label: str) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise TenhouImportError(f"{label} is not executable: {path}")


def convert_mjlog(
    metadata: TenhouReplayMetadata,
    converter_executable: Path,
    output_dir: Path,
    *,
    timeout: int,
) -> Path:
    _require_executable(converter_executable, "Mahjong-Replay-Converter")
    conversion_dir = output_dir / "converted" / f"{_safe_stem(metadata.path)}.{metadata.source_sha256[:12]}"
    conversion_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MAHJONG_REPLAY_CONVERTER_CONFIG_DIR"] = str(conversion_dir / "config")
    before = set(conversion_dir.glob("*.json"))
    _run(
        [str(converter_executable), "convert-file", str(metadata.path),
         "--output", str(conversion_dir), "--format", "tenhou6"],
        env=env, timeout=timeout,
    )
    candidates = sorted(conversion_dir.glob("*.json"))
    new_candidates = [path for path in candidates if path not in before]
    if len(new_candidates) != 1:
        raise TenhouImportError("converter did not produce exactly one Tenhou/6 JSON file")
    source_payload = json.loads(new_candidates[0].read_text(encoding="utf-8"))
    normalized = normalize_tenhou6_payload(source_payload, game_id=metadata.game_id)
    output_path = conversion_dir / f"{_safe_stem(metadata.path)}.normalized.json"
    output_path.write_text(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return output_path


def reviewer_version(reviewer_executable: Path, *, timeout: int) -> str:
    _require_executable(reviewer_executable, "mjai-reviewer")
    completed = _run([str(reviewer_executable), "--version"], env=os.environ.copy(), timeout=timeout)
    match = re.search(r"(\d+\.\d+\.\d+)", completed.stdout + completed.stderr)
    if not match:
        raise TenhouImportError("could not determine mjai-reviewer version")
    return match.group(1)


def _mjai_conversion(
    reviewer_executable: Path,
    tenhou_json: Path,
    player_id: int,
    output_dir: Path,
    *,
    timeout: int,
) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mjai_path = output_dir / f"{tenhou_json.stem}.player{player_id}.mjai"
    _run(
        [str(reviewer_executable), "--in-file", str(tenhou_json), "--player-id", str(player_id),
         "--engine", "mortal", "--no-review", "--mjai-out", str(mjai_path), "--no-open"],
        env=os.environ.copy(), timeout=timeout,
    )
    try:
        events = [json.loads(line) for line in mjai_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TenhouImportError("mjai-reviewer produced invalid MJAI JSON Lines") from exc
    if not events:
        raise TenhouImportError("mjai-reviewer produced an empty MJAI log")
    return mjai_path, hashlib.sha256(_canonical(events).encode()).hexdigest()


def _existing_review(
    connection,
    *,
    game_id: str,
    log_sha256: str,
    source_sha256: str,
    player_id: int,
    reviewer_version_value: str,
    temperature: float,
    model_tag: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT r.id, r.model_tag
        FROM reviews r JOIN games g ON g.id = r.game_id
        WHERE (
            g.log_sha256 = ?
            OR g.source_sha256 = ?
            OR (g.source_sha256 IS NULL AND g.source_game_id = ?)
        )
          AND r.player_id = ? AND lower(r.engine) = 'mortal'
          AND r.reviewer_version = ? AND r.temperature = ?
          AND r.model_tag = ?
        """,
        (log_sha256, source_sha256, game_id, player_id, reviewer_version_value, temperature, model_tag),
    ).fetchall()
    return bool(rows)


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted([*path.glob("*.mjlog"), *path.glob("*.xml.gz")])
    raise TenhouImportError(f"input path does not exist: {path}")


def analyze_tenhou_path(
    input_path: Path,
    database_path: Path,
    player_id: int | None,
    *,
    converter_executable: Path,
    analysis_config: AnalysisConfig,
    output_dir: Path,
    model_tag: str,
    game_id: str | None = None,
    timeout: int = 1800,
    identity_config: TenhouIdentityConfig | None = None,
) -> TenhouBatchResult:
    if player_id is not None and not 0 <= player_id <= 3:
        raise ValidationError("--player-id must be between 0 and 3")
    paths = _files(input_path)
    if input_path.is_dir() and game_id is not None:
        raise ValidationError("--game-id can only be used with one input file")
    version = reviewer_version(analysis_config.reviewer_executable, timeout=timeout)
    connection = connect(database_path)
    initialize(connection)
    analyzed = skipped = failures = detected = decisions = 0
    errors: list[str] = []
    try:
        for path in paths:
            try:
                metadata = inspect_mjlog(path, game_id=game_id)
                detected += 1
                resolved_player_id = resolve_player_id(
                    metadata.player_names, identity_config, player_id,
                    tw_player_id=metadata.tw_player_id,
                )
                normalized_path = convert_mjlog(metadata, converter_executable, output_dir, timeout=timeout)
                _, log_sha = _mjai_conversion(
                    analysis_config.reviewer_executable, normalized_path, resolved_player_id,
                    output_dir / "preflight", timeout=timeout,
                )
                if _existing_review(
                    connection, game_id=metadata.game_id, log_sha256=log_sha,
                    source_sha256=metadata.source_sha256, player_id=resolved_player_id,
                    reviewer_version_value=version, temperature=analysis_config.temperature,
                    model_tag=model_tag,
                ):
                    skipped += 1
                    continue
                result: AnalysisResult = analyze_log(
                    normalized_path, database_path, resolved_player_id, analysis_config,
                    game_id=metadata.game_id, game_type=metadata.game_type,
                    rule_context=metadata.rule_context, source_sha256=metadata.source_sha256,
                )
                if result.import_status != "imported":
                    raise TenhouImportError(
                        f"unexpected import status for new replay: {result.import_status}"
                    )
                review = json.loads(result.review_path.read_text(encoding="utf-8"))
                decisions += int(review["review"]["total_reviewed"])
                analyzed += 1
            except (OSError, AnalyzerError, ValueError, KeyError, TypeError) as exc:
                failures += 1
                errors.append(f"{path}: {exc}")
    finally:
        connection.close()
    return TenhouBatchResult(
        input_files=len(paths), detected_games=detected, analyzed_games=analyzed,
        skipped_duplicates=skipped, failures=failures, registered_decisions=decisions,
        errors=tuple(errors),
    )
