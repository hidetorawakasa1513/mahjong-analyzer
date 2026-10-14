from __future__ import annotations

import copy
import re
from typing import Any

from .errors import ValidationError


_DIGITS = re.compile(r"^[0-9]+$")


class TenhouCompatibilityError(ValidationError):
    """Raised when a Tenhou/6 action cannot be safely normalized."""


def _validate_tile_bytes(value: str, *, label: str) -> None:
    if len(value) % 2 or not _DIGITS.fullmatch(value):
        raise TenhouCompatibilityError(f"{label} contains invalid tile bytes: {value!r}")
    for offset in range(0, len(value), 2):
        tile = int(value[offset:offset + 2])
        if not 0 <= tile <= 60:
            raise TenhouCompatibilityError(f"{label} contains unsupported tile code: {tile}")


def _normalize_naki(value: str, *, label: str) -> str:
    if value.startswith("r"):
        if len(value) != 3 or not value[1:].isdigit():
            raise TenhouCompatibilityError(f"{label} has invalid reach marker: {value!r}")
        _validate_tile_bytes(value[1:], label=label)
        return value

    markers = [(marker, value.find(marker)) for marker in "cpmka" if marker in value]
    if len(markers) != 1:
        raise TenhouCompatibilityError(f"{label} has an unknown meld marker: {value!r}")
    marker, position = markers[0]
    expected_length = 7 if marker in {"c", "p"} else 9
    if len(value) != expected_length:
        raise TenhouCompatibilityError(f"{label} has invalid {marker} meld length: {value!r}")
    allowed_positions = {
        "c": {0},
        "p": {0, 2, 4},
        "m": {0, 2, 6},
        "k": {0, 2, 4},
        # mjai-reviewer expects the concealed-kan marker at byte position 6.
        "a": {0, 6},
    }[marker]
    if position not in allowed_positions:
        raise TenhouCompatibilityError(
            f"{label} has an unsupported {marker} marker position: {value!r}"
        )
    digits = value.replace(marker, "", 1)
    _validate_tile_bytes(digits, label=label)
    if marker == "a" and position == 0:
        # Converter v0.2.3 emits `a` before all four tiles. mjai-reviewer
        # 1.5.10 parses the same four tiles with `a` before the fourth tile.
        return digits[:6] + "a" + digits[6:]
    return value


def normalize_tenhou6_payload(payload: dict[str, Any], *, game_id: str | None = None) -> dict[str, Any]:
    """Validate Tenhou/6 action syntax and normalize known tool incompatibilities."""
    if not isinstance(payload, dict):
        raise TenhouCompatibilityError("Tenhou/6 JSON root must be an object")
    names = payload.get("name")
    rounds = payload.get("log")
    if not isinstance(names, list) or len(names) != 4:
        raise TenhouCompatibilityError("Tenhou/6 JSON must contain four player names")
    if not isinstance(rounds, list) or not rounds:
        raise TenhouCompatibilityError("Tenhou/6 JSON must contain at least one round")

    normalized = copy.deepcopy(payload)
    for round_index, raw_round in enumerate(normalized["log"]):
        if not isinstance(raw_round, list) or len(raw_round) < 17:
            raise TenhouCompatibilityError(f"round {round_index} is not a complete Tenhou/6 round")
        for field_index in (5, 6, 8, 9, 11, 12, 14, 15):
            field = raw_round[field_index]
            if not isinstance(field, list):
                raise TenhouCompatibilityError(
                    f"round {round_index} action field {field_index} must be an array"
                )
            for item_index, item in enumerate(field):
                if isinstance(item, str):
                    field[item_index] = _normalize_naki(
                        item, label=f"round {round_index} field {field_index} item {item_index}"
                    )
                elif isinstance(item, int):
                    if not 0 <= item <= 60:
                        raise TenhouCompatibilityError(
                            f"round {round_index} contains unsupported tile code: {item}"
                        )
                else:
                    raise TenhouCompatibilityError(
                        f"round {round_index} action item has unsupported type"
                    )
    if game_id is not None:
        if not game_id.strip():
            raise TenhouCompatibilityError("game_id must not be empty")
        normalized["ref"] = game_id
    return normalized
