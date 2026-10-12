from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mahjong_analyzer.errors import AnalyzerError, ValidationError
from mahjong_analyzer.runner import AnalysisConfig, analyze_log, validate_tenhou6_file

from test_phase1 import payload


def tenhou_file(path: Path) -> Path:
    path.write_text(json.dumps({
        "ver": "2.3",
        "ref": "game-1",
        "name": ["A", "B", "C", "D"],
        "log": [[[0, 0, 0], [25000, 25000, 25000, 25000], [11], [], [11] * 13,
                  [12], [12], [21] * 13, [22], [22], [31] * 13, [32], [32],
                  [41] * 13, [42], [42], ["流局", [0, 0, 0, 0]]]]
    }), encoding="utf-8")
    return path


def config(tmp_path: Path) -> AnalysisConfig:
    reviewer = tmp_path / "reviewer"
    mortal = tmp_path / "mortal"
    mortal_cfg = tmp_path / "config.toml"
    reviewer.write_text("", encoding="utf-8")
    mortal.write_text("", encoding="utf-8")
    reviewer.chmod(0o755)
    mortal.chmod(0o755)
    mortal_cfg.write_text("[control]\n", encoding="utf-8")
    return AnalysisConfig(reviewer, mortal, mortal_cfg, tmp_path / "outputs")


def test_tenhou_validation_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        validate_tenhou6_file(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError):
        validate_tenhou6_file(bad)


def test_player_id_range_and_missing_executable(tmp_path: Path) -> None:
    source = tenhou_file(tmp_path / "input.json")
    with pytest.raises(ValidationError):
        analyze_log(source, tmp_path / "db.sqlite3", 4, config(tmp_path))
    missing = config(tmp_path)
    missing = AnalysisConfig(tmp_path / "missing", missing.mortal_executable,
                             missing.mortal_config, missing.output_dir)
    with pytest.raises(AnalyzerError, match="mjai-reviewer"):
        analyze_log(source, tmp_path / "db.sqlite3", 0, missing)


def test_runner_uses_argument_vector_and_imports_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tenhou_file(tmp_path / "input.json")
    review = payload()
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        output = Path(command[command.index("--out-file") + 1])
        mjai = Path(command[command.index("--mjai-out") + 1])
        output.write_text(json.dumps(review), encoding="utf-8")
        mjai.write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    database = tmp_path / "db.sqlite3"
    first = analyze_log(source, database, 0, config(tmp_path))
    second = analyze_log(source, database, 0, config(tmp_path))
    assert first.import_status == "imported"
    assert second.import_status == "duplicate"
    assert calls[0][1]["shell"] is False
    assert "--player-id" in calls[0][0]
    assert calls[0][1]["timeout"] == 900


def test_runner_failure_does_not_create_database_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tenhou_file(tmp_path / "input.json")

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 2, "", "engine failed")

    monkeypatch.setattr(subprocess, "run", fail_run)
    with pytest.raises(AnalyzerError, match="status 2"):
        analyze_log(source, tmp_path / "db.sqlite3", 0, config(tmp_path))
    assert not (tmp_path / "db.sqlite3").exists()


def test_corrupt_review_is_not_imported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tenhou_file(tmp_path / "input.json")

    def corrupt_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[command.index("--out-file") + 1]).write_text("{}", encoding="utf-8")
        Path(command[command.index("--mjai-out") + 1]).write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", corrupt_run)
    with pytest.raises(AnalyzerError, match="invalid review JSON"):
        analyze_log(source, tmp_path / "db.sqlite3", 0, config(tmp_path))
    assert not (tmp_path / "db.sqlite3").exists()
