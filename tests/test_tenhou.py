from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from mahjong_analyzer.errors import AnalyzerError
from mahjong_analyzer.importer import ImportMetadata, import_review, normalize_review
from mahjong_analyzer.runner import AnalysisConfig, AnalysisResult
from mahjong_analyzer.schema import connect
import mahjong_analyzer.tenhou as tenhou

from test_phase1 import payload


def _mjlog(path: Path) -> Path:
    xml = (
        '<mjloggm ver="2.3"><GO type="9"/><TAIKYOKU oya="0"/>'
        '<INIT seed="0,0,0,0,0,11" ten="250,250,250,250"/>'
        '<RYUUKYOKU sc="0,0,0,0"/></mjloggm>'
    ).encode()
    path.write_bytes(gzip.compress(xml))
    return path


def _config(tmp_path: Path) -> AnalysisConfig:
    return AnalysisConfig(
        reviewer_executable=tmp_path / "reviewer",
        mortal_executable=tmp_path / "mortal",
        mortal_config=tmp_path / "mortal.toml",
        output_dir=tmp_path / "analysis",
    )


def test_tenhou_batch_skips_duplicate_before_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _mjlog(tmp_path / "2026101418gm-0009-0000-b87423b0&tw=3.mjlog")
    second = _mjlog(tmp_path / "2026101418gm-0009-0000-b87423b0-copy&tw=3.mjlog")
    normalized = tmp_path / "normalized.json"
    normalized.write_text("{}", encoding="utf-8")
    calls = 0

    monkeypatch.setattr(tenhou, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    monkeypatch.setattr(tenhou, "convert_mjlog", lambda *args, **kwargs: normalized)
    monkeypatch.setattr(
        tenhou, "_mjai_conversion", lambda *args, **kwargs: (tmp_path / "x.mjai", "mjai-hash")
    )

    def fake_analyze(path: Path, database: Path, player: int, config: AnalysisConfig, **kwargs: object) -> AnalysisResult:
        nonlocal calls
        calls += 1
        value = payload(game_id=str(kwargs["game_id"]), player_id=player)
        value["version"] = "1.5.10"
        value["review"]["model_tag"] = "model-a"
        connection = connect(database)
        try:
            import_review(
                connection,
                normalize_review(
                    json.dumps(value).encode(),
                    ImportMetadata(
                        game_id=str(kwargs["game_id"]), player_id=player,
                        source_sha256=str(kwargs["source_sha256"]),
                    ),
                ),
            )
        finally:
            connection.close()
        review_path = tmp_path / f"review-{calls}.json"
        review_path.write_text(json.dumps(value), encoding="utf-8")
        return AnalysisResult(tmp_path / f"mjai-{calls}.jsonl", review_path, "imported")

    monkeypatch.setattr(tenhou, "analyze_log", fake_analyze)
    result = tenhou.analyze_tenhou_path(
        tmp_path, tmp_path / "db.sqlite3", 3, converter_executable=tmp_path / "converter",
        analysis_config=_config(tmp_path), output_dir=tmp_path / "out", model_tag="model-a",
    )
    assert result.input_files == 2
    assert result.detected_games == 2
    assert result.analyzed_games == 1
    assert result.skipped_duplicates == 1
    assert result.registered_decisions == 2
    assert calls == 1


def test_tenhou_batch_failure_does_not_register_partial_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mjlog(tmp_path / "2026101418gm-0009-0000-b87423b0&tw=3.mjlog")
    normalized = tmp_path / "normalized.json"
    normalized.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(tenhou, "reviewer_version", lambda *args, **kwargs: "1.5.10")
    monkeypatch.setattr(tenhou, "convert_mjlog", lambda *args, **kwargs: normalized)
    monkeypatch.setattr(
        tenhou, "_mjai_conversion", lambda *args, **kwargs: (tmp_path / "x.mjai", "mjai-hash")
    )
    monkeypatch.setattr(tenhou, "analyze_log", lambda *args, **kwargs: (_ for _ in ()).throw(AnalyzerError("failed")))

    result = tenhou.analyze_tenhou_path(
        tmp_path / "2026101418gm-0009-0000-b87423b0&tw=3.mjlog", tmp_path / "db.sqlite3", 3,
        converter_executable=tmp_path / "converter", analysis_config=_config(tmp_path),
        output_dir=tmp_path / "out", model_tag="model-a",
    )
    assert result.failures == 1
    connection = connect(tmp_path / "db.sqlite3")
    try:
        assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
    finally:
        connection.close()
