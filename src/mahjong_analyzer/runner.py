from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .errors import AnalyzerError, ValidationError
from .importer import ImportMetadata, import_file, normalize_review
from .report import summary
from .schema import connect


class AnalysisError(AnalyzerError):
    """Raised when the external reviewer pipeline fails safely."""


@dataclass(frozen=True)
class AnalysisConfig:
    reviewer_executable: Path
    mortal_executable: Path
    mortal_config: Path
    output_dir: Path
    temperature: float = 0.1
    timeout_seconds: int = 900
    python_path: Path | None = None


@dataclass(frozen=True)
class AnalysisResult:
    mjai_path: Path
    review_path: Path
    import_status: str


def validate_tenhou6_file(path: Path) -> dict:
    if not path.is_file():
        raise ValidationError(f"input file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("input must be a readable UTF-8 Tenhou/6 JSON file") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Tenhou/6 JSON root must be an object")
    if not isinstance(payload.get("name"), list) or len(payload["name"]) != 4:
        raise ValidationError("Tenhou/6 JSON must contain four player names")
    if not isinstance(payload.get("log"), list) or not payload["log"]:
        raise ValidationError("Tenhou/6 JSON must contain at least one round")
    if "ref" in payload and not isinstance(payload["ref"], str):
        raise ValidationError("Tenhou/6 ref must be a string when present")
    return payload


def _require_executable(path: Path, label: str) -> None:
    if not path.is_file():
        raise AnalysisError(f"{label} does not exist: {path}")
    if not os.access(path, os.X_OK):
        raise AnalysisError(f"{label} is not executable: {path}")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise AnalysisError(f"{label} does not exist: {path}")


def _game_id(payload: dict, explicit: str | None) -> str | None:
    value = payload.get("ref")
    if value is None:
        return explicit
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Tenhou/6 ref must be a non-empty string when present")
    if explicit is not None and explicit != value:
        raise ValidationError("--game-id does not match Tenhou/6 ref")
    return value


def _safe_stem(path: Path) -> str:
    stem = "".join(character if character.isalnum() or character in "-_" else "_"
                   for character in path.stem)
    return stem[:80] or "replay"


def _command(
    config: AnalysisConfig,
    input_path: Path,
    mjai_path: Path,
    review_path: Path,
    player_id: int,
) -> list[str]:
    return [
        str(config.reviewer_executable),
        "--in-file", str(input_path),
        "--player-id", str(player_id),
        "--engine", "mortal",
        "--mortal-exe", str(config.mortal_executable),
        "--mortal-cfg", str(config.mortal_config),
        "--temperature", str(config.temperature),
        "--json",
        "--out-file", str(review_path),
        "--mjai-out", str(mjai_path),
        "--no-open",
    ]


def _environment(config: AnalysisConfig) -> dict[str, str]:
    environment = os.environ.copy()
    if config.python_path is not None:
        current = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(config.python_path) + (os.pathsep + current if current else "")
    return environment


def analyze_log(
    input_path: Path,
    database_path: Path,
    player_id: int,
    config: AnalysisConfig,
    *,
    game_id: str | None = None,
    played_at: str | None = None,
    game_type: str | None = None,
    rule_context: str | None = None,
) -> AnalysisResult:
    if not 0 <= player_id <= 3:
        raise ValidationError("player_id must be between 0 and 3")
    if not 0 < config.temperature:
        raise ValidationError("temperature must be greater than zero")
    if config.timeout_seconds <= 0:
        raise ValidationError("timeout must be greater than zero")
    payload = validate_tenhou6_file(input_path)
    input_game_id = _game_id(payload, game_id)
    resolved_input = input_path.resolve()
    _require_executable(config.reviewer_executable, "mjai-reviewer")
    _require_executable(config.mortal_executable, "Mortal executable")
    _require_file(config.mortal_config, "Mortal config")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(resolved_input)
    mjai_path = config.output_dir / f"{stem}.player{player_id}.mjai"
    review_path = config.output_dir / f"{stem}.player{player_id}.review.json"
    # Prevent a failed reviewer run from being mistaken for a previous successful output.
    mjai_path.unlink(missing_ok=True)
    review_path.unlink(missing_ok=True)
    command = _command(config, resolved_input, mjai_path, review_path, player_id)
    try:
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            env=_environment(config),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AnalysisError("mjai-reviewer execution failed or timed out") from exc
    if completed.returncode != 0:
        raise AnalysisError(f"mjai-reviewer exited with status {completed.returncode}")
    if not review_path.is_file():
        raise AnalysisError("mjai-reviewer did not produce a review JSON")
    if not mjai_path.is_file():
        raise AnalysisError("mjai-reviewer did not produce an MJAI log")
    try:
        normalize_review(
            review_path.read_bytes(),
            ImportMetadata(game_id=input_game_id, player_id=player_id),
        )
    except Exception as exc:
        raise AnalysisError("mjai-reviewer produced an invalid review JSON") from exc
    metadata = ImportMetadata(game_id=input_game_id, player_id=player_id,
                              played_at=played_at, game_type=game_type, rule_context=rule_context)
    connection = connect(database_path)
    try:
        status = import_file(connection, review_path, metadata)
    finally:
        connection.close()
    return AnalysisResult(mjai_path=mjai_path, review_path=review_path, import_status=status)


def command_for_display(command: Sequence[str]) -> str:
    """Return a log-safe command string without secrets."""
    return " ".join(shlex_quote(part) for part in command)


def shlex_quote(value: str) -> str:
    # Avoid importing or logging subprocess output; this only quotes arguments.
    if value and all(character.isalnum() or character in "@%_+=:,./-" for character in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"
