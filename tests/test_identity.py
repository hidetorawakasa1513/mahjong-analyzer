from __future__ import annotations

import json
from pathlib import Path

import pytest

from mahjong_analyzer.errors import ValidationError
from mahjong_analyzer.identity import IdentityResolutionError, TenhouIdentityConfig, load_tenhou_identity, resolve_player_id


@pytest.mark.parametrize("seat", range(4))
def test_resolves_each_seat_by_exact_name(seat: int) -> None:
    names = ("A", "B", "C", "D")
    assert resolve_player_id(names, TenhouIdentityConfig("account", names[seat])) == seat


def test_config_loads_and_decoded_name_is_used(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tenhou": {"account_id": "ID", "player_name": "トラ"}}), encoding="utf-8")
    config = load_tenhou_identity(path)
    assert resolve_player_id(("A", "トラ", "C", "D"), config) == 1


def test_missing_or_ambiguous_name_is_held() -> None:
    config = TenhouIdentityConfig("account", "A")
    with pytest.raises(IdentityResolutionError):
        resolve_player_id(("B", "C", "D", "E"), config)
    with pytest.raises(IdentityResolutionError):
        resolve_player_id(("A", "A", "D", "E"), config)


def test_tw_mismatch_is_held_and_missing_tw_is_allowed() -> None:
    config = TenhouIdentityConfig("account", "A")
    with pytest.raises(IdentityResolutionError):
        resolve_player_id(("A", "B", "C", "D"), config, tw_player_id=3)
    assert resolve_player_id(("A", "B", "C", "D"), config) == 0


def test_manual_player_id_must_match_xml() -> None:
    config = TenhouIdentityConfig("account", "A")
    with pytest.raises(IdentityResolutionError):
        resolve_player_id(("A", "B", "C", "D"), config, manual_player_id=1)


def test_invalid_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tenhou": {"account_id": ""}}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_tenhou_identity(path)
