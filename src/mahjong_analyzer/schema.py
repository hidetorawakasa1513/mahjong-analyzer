from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            source_game_id TEXT,
            log_sha256 TEXT,
            played_at TEXT,
            game_type TEXT,
            rule_context TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(source, source_game_id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
            player_id INTEGER NOT NULL CHECK(player_id BETWEEN 0 AND 3),
            engine TEXT NOT NULL,
            reviewer_version TEXT,
            model_tag TEXT,
            model_identity TEXT,
            grp_identity TEXT,
            temperature REAL,
            rating REAL,
            total_reviewed INTEGER NOT NULL CHECK(total_reviewed >= 0),
            total_matches INTEGER NOT NULL CHECK(total_matches >= 0),
            review_sha256 TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY,
            review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
            decision_index INTEGER NOT NULL CHECK(decision_index >= 0),
            kyoku_index INTEGER,
            junme INTEGER,
            shanten INTEGER,
            actual_action TEXT,
            expected_action TEXT,
            is_equal INTEGER CHECK(is_equal IN (0, 1) OR is_equal IS NULL),
            actual_probability REAL CHECK(
                actual_probability IS NULL OR
                (actual_probability >= 0.0 AND actual_probability <= 1.0)
            ),
            is_comparable INTEGER NOT NULL CHECK(is_comparable IN (0, 1)),
            missing_reason TEXT,
            UNIQUE(review_id, decision_index)
        );

        INSERT INTO schema_meta(key, value)
        VALUES ('schema_version', '1')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """
    )
    connection.commit()
