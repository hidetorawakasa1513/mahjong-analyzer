from __future__ import annotations

from pathlib import Path

import pytest
import gzip

import mahjong_analyzer.workflow as workflow
from mahjong_analyzer.runner import AnalysisConfig
from mahjong_analyzer.tenhou import TenhouBatchResult


def _config(tmp_path: Path) -> AnalysisConfig:
    return AnalysisConfig(
        reviewer_executable=tmp_path / "reviewer",
        mortal_executable=tmp_path / "mortal",
        mortal_config=tmp_path / "mortal.toml",
        output_dir=tmp_path / "analysis",
    )


def _mjlog(path: Path, content: bytes = b"replay") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = (
        f'<mjloggm ver="2.3"><UN n0="A" n1="B" n2="C" n3="D"/>'
        f'<GO type="9"/><TAIKYOKU oya="0"/><INIT seed="{content.hex()},0,0,0,0,11"/>'
        '<RYUUKYOKU sc="0,0,0,0"/></mjloggm>'
    ).encode()
    path.write_bytes(gzip.compress(xml))
    return path


def test_empty_inbox_creates_workflow_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflow, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    result = workflow.organize_tenhou_inbox(
        tmp_path / "tenhou", tmp_path / "db.sqlite3", player_id=3,
        converter_executable=tmp_path / "converter", analysis_config=_config(tmp_path),
        model_tag="model", output_dir=tmp_path / "output",
    )
    assert result.input_files == 0
    assert result.failures == 0
    assert (tmp_path / "tenhou/inbox").is_dir()
    assert (tmp_path / "tenhou/processed").is_dir()
    assert (tmp_path / "tenhou/failed").is_dir()


def test_successful_replay_moves_to_processed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _mjlog(tmp_path / "tenhou/inbox/2026101418gm-0009-0000-b87423b0.mjlog")
    monkeypatch.setattr(workflow, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    counts = iter([(0, 0, 0), (1, 1, 4)])
    monkeypatch.setattr(workflow, "_db_counts", lambda *args, **kwargs: next(counts))
    monkeypatch.setattr(
        workflow, "analyze_tenhou_path",
        lambda *args, **kwargs: TenhouBatchResult(1, 1, 1, 0, 0, 4, ()),
    )
    result = workflow.organize_tenhou_inbox(
        tmp_path / "tenhou", tmp_path / "db.sqlite3", player_id=3,
        converter_executable=tmp_path / "converter", analysis_config=_config(tmp_path),
        model_tag="model", output_dir=tmp_path / "output",
    )
    assert result.analyzed_games == 1
    assert result.processed_moved == 1
    assert not source.exists()
    assert (tmp_path / "tenhou/processed/2026101418gm-0009-0000-b87423b0.mjlog").exists()


def test_same_file_is_removed_only_after_registered_duplicate_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _mjlog(tmp_path / "tenhou/inbox/2026101418gm-0009-0000-b87423b0.mjlog")
    processed = _mjlog(tmp_path / "tenhou/processed/2026101418gm-0009-0000-b87423b0.mjlog")
    monkeypatch.setattr(workflow, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    monkeypatch.setattr(workflow, "_successful_source_exists", lambda *args, **kwargs: True)
    result = workflow.organize_tenhou_inbox(
        tmp_path / "tenhou", tmp_path / "db.sqlite3", player_id=3,
        converter_executable=tmp_path / "converter", analysis_config=_config(tmp_path),
        model_tag="model", output_dir=tmp_path / "output",
    )
    assert result.skipped_duplicates == 1
    assert result.duplicate_removed == 1
    assert not source.exists()
    assert processed.exists()


def test_failure_moves_replay_and_writes_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _mjlog(tmp_path / "tenhou/inbox/2026101418gm-0009-0000-b87423b0.mjlog")
    monkeypatch.setattr(workflow, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    monkeypatch.setattr(workflow, "_db_counts", lambda *args, **kwargs: (0, 0, 0))
    monkeypatch.setattr(
        workflow, "analyze_tenhou_path",
        lambda *args, **kwargs: TenhouBatchResult(1, 1, 0, 0, 1, 0, ("invalid replay",)),
    )
    result = workflow.organize_tenhou_inbox(
        tmp_path / "tenhou", tmp_path / "db.sqlite3", player_id=3,
        converter_executable=tmp_path / "converter", analysis_config=_config(tmp_path),
        model_tag="model", output_dir=tmp_path / "output",
    )
    assert result.failures == 1
    failed = tmp_path / "tenhou/failed/2026101418gm-0009-0000-b87423b0.mjlog"
    assert failed.exists()
    assert "invalid replay" in (tmp_path / "tenhou/failed/2026101418gm-0009-0000-b87423b0.mjlog.error.json").read_text()
    assert not source.exists()


def test_migration_requires_registered_review_and_never_calls_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _mjlog(tmp_path / "existing.mjlog")
    monkeypatch.setattr(
        workflow, "_preflight_registered",
        lambda *args, **kwargs: (True, "source-sha", "log-sha"),
    )
    monkeypatch.setattr(workflow, "_backfill_source_hash", lambda *args, **kwargs: True)
    result = workflow.migrate_existing_tenhou(
        source, tmp_path / "tenhou", tmp_path / "db.sqlite3", player_id=3,
        converter_executable=tmp_path / "converter", reviewer_executable=tmp_path / "reviewer",
        output_dir=tmp_path / "output", model_tag="model", temperature=0.1, timeout=10,
    )
    assert result["status"] == "migrated"
    assert not source.exists()
    assert (tmp_path / "tenhou/processed/existing.mjlog").exists()


def test_different_content_does_not_overwrite_same_name(tmp_path: Path) -> None:
    directory = tmp_path / "processed"
    directory.mkdir()
    original = _mjlog(directory / "game.mjlog", b"original")
    destination = workflow._destination(directory, Path("game.mjlog"), "new-sha")
    assert destination != original
    assert destination.name == "game.new-sha.mjlog"
