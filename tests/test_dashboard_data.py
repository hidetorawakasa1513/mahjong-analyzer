from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mahjong_analyzer.dashboard.data import connect_readonly, home_data, load_dashboard_paths
from mahjong_analyzer.schema import connect, initialize


def test_readonly_connection_does_not_create_or_write(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    writable = connect(db_path)
    initialize(writable)
    writable.close()

    readonly = connect_readonly(db_path)
    assert readonly.execute("PRAGMA query_only").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError):
        readonly.execute("CREATE TABLE should_not_exist (id INTEGER)")
    readonly.close()
    assert not (tmp_path / "should_not_exist").exists()


def test_missing_database_is_reported_without_creation(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        connect_readonly(path)
    assert not path.exists()


def test_home_data_reads_empty_database(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    writable = connect(db_path)
    initialize(writable)
    writable.close()
    readonly = connect_readonly(db_path)
    value = home_data(readonly)
    assert value["games"] == 0
    assert value["decisions"] == 0
    assert value["summaries"] == []
    readonly.close()


def test_dashboard_paths_resolve_relative_to_project_root(tmp_path: Path) -> None:
    config_path = tmp_path / "local_data" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(
        '{"tenhou": {"account_id": "hidden", "player_name": "hidden"}, '
        '"dashboard": {"database": "local_data/db.sqlite3", '
        '"review_root": "local_data/reviews", "source_root": "data/raw/tenhou"}}',
        encoding="utf-8",
    )
    paths = load_dashboard_paths(config_path, project_root=tmp_path)
    assert paths.database == tmp_path / "local_data/db.sqlite3"
    assert paths.review_root == tmp_path / "local_data/reviews"
    assert paths.source_root == tmp_path / "data/raw/tenhou"


def test_dashboard_paths_keep_defaults_when_dashboard_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "local_data" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text('{"tenhou": {"account_id": "hidden"}}', encoding="utf-8")
    paths = load_dashboard_paths(config_path, project_root=tmp_path)
    assert paths.database == tmp_path / "local_data/mahjong_analyzer.sqlite3"
