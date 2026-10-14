from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ValidationError


class IdentityResolutionError(ValidationError):
    """Raised when a replay cannot be safely assigned to the configured player."""


@dataclass(frozen=True)
class TenhouIdentityConfig:
    account_id: str
    player_name: str | None


def load_tenhou_identity(path: Path) -> TenhouIdentityConfig:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read local Tenhou config: {path}") from exc
    tenhou = payload.get("tenhou") if isinstance(payload, dict) else None
    if not isinstance(tenhou, dict):
        raise ValidationError("local Tenhou config must contain a tenhou object")
    account_id = tenhou.get("account_id")
    player_name = tenhou.get("player_name")
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValidationError("local Tenhou config account_id is required")
    if player_name is not None and (not isinstance(player_name, str) or not player_name):
        raise ValidationError("local Tenhou config player_name must be a non-empty string or null")
    return TenhouIdentityConfig(account_id=account_id, player_name=player_name)


def resolve_player_id(
    player_names: tuple[str, ...],
    config: TenhouIdentityConfig | None,
    manual_player_id: int | None = None,
    *,
    tw_player_id: int | None = None,
) -> int:
    if manual_player_id is not None and not 0 <= manual_player_id <= 3:
        raise ValidationError("player_id must be between 0 and 3")
    if config is None:
        if manual_player_id is None:
            raise IdentityResolutionError("Tenhou player identity config is required for automatic seat detection")
        resolved = manual_player_id
    else:
        if config.player_name is None:
            raise IdentityResolutionError("Tenhou config player_name is required for automatic seat detection")
        matches = [index for index, name in enumerate(player_names) if name == config.player_name]
        if len(matches) != 1:
            raise IdentityResolutionError("configured Tenhou player name is missing or ambiguous in this replay")
        resolved = matches[0]
        if manual_player_id is not None and manual_player_id != resolved:
            raise IdentityResolutionError("manual player_id does not match the XML identity")
    if tw_player_id is not None and tw_player_id != resolved:
        raise IdentityResolutionError("filename tw view does not match the XML identity")
    return resolved
