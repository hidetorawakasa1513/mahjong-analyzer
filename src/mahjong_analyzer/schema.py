from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3


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
            source_sha256 TEXT,
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
            review_identity_sha256 TEXT,
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

        CREATE TABLE IF NOT EXISTS decision_contexts (
            id INTEGER PRIMARY KEY,
            decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
            extractor_version TEXT NOT NULL,
            context_status TEXT NOT NULL CHECK(context_status IN ('complete', 'partial', 'unmapped', 'invalid')),
            mapping_kind TEXT NOT NULL CHECK(mapping_kind IN ('event', 'non_action_opportunity', 'unmapped')),
            status_reason TEXT,
            source_event_index INTEGER,
            source_round_event_index INTEGER,
            round_index INTEGER,
            bakaze TEXT,
            kyoku INTEGER,
            honba INTEGER,
            turn_number INTEGER,
            hand_json TEXT,
            fuuros_json TEXT,
            shanten_before INTEGER,
            opponent_riichi_count INTEGER,
            riichi_seats_json TEXT,
            self_riichi INTEGER CHECK(self_riichi IN (0, 1) OR self_riichi IS NULL),
            is_dealer INTEGER CHECK(is_dealer IN (0, 1) OR is_dealer IS NULL),
            scores_before_json TEXT,
            rank_before INTEGER,
            gap_to_first INTEGER,
            gap_to_last INTEGER,
            gap_to_above INTEGER,
            gap_to_below INTEGER,
            action_category TEXT,
            source_sha256 TEXT,
            mjai_log_sha256 TEXT,
            extraction_note TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(decision_id, extractor_version)
        );

        CREATE INDEX IF NOT EXISTS decision_contexts_source_event_idx
            ON decision_contexts(source_event_index);
        CREATE INDEX IF NOT EXISTS decision_contexts_action_idx
            ON decision_contexts(action_category);
        CREATE INDEX IF NOT EXISTS decision_contexts_turn_idx
            ON decision_contexts(turn_number);
        CREATE INDEX IF NOT EXISTS decision_contexts_shanten_idx
            ON decision_contexts(shanten_before);
        CREATE INDEX IF NOT EXISTS decision_contexts_riichi_idx
            ON decision_contexts(opponent_riichi_count);

        INSERT INTO schema_meta(key, value)
        VALUES ('schema_version', '3')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
    game_columns = {row[1] for row in connection.execute("PRAGMA table_info(games)")}
    if "source_sha256" not in game_columns:
        connection.execute("ALTER TABLE games ADD COLUMN source_sha256 TEXT")
    if "review_identity_sha256" not in columns:
        connection.execute("ALTER TABLE reviews ADD COLUMN review_identity_sha256 TEXT")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS reviews_identity_unique
        ON reviews(review_identity_sha256)
        WHERE review_identity_sha256 IS NOT NULL
        """
    )
    connection.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")
    connection.commit()
