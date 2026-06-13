from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from personas import DEFAULT_COUNCILS, DEFAULT_PERSONAS


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).with_name("friend_chat.db")))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                topic_summary TEXT NOT NULL,
                council_id TEXT NOT NULL DEFAULT 'friend',
                discussion_summary TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                author_persona_id TEXT NOT NULL,
                parent_comment_id INTEGER,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_comment_id) REFERENCES comments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS personas (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                avatar_label TEXT NOT NULL,
                personality TEXT NOT NULL,
                interests TEXT NOT NULL,
                speech_style TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS councils (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                simulation_style TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS council_personas (
                council_id TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (council_id, persona_id),
                FOREIGN KEY (council_id) REFERENCES councils(id) ON DELETE CASCADE,
                FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS persona_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id TEXT NOT NULL UNIQUE,
                memory TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
            CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_comment_id);
            CREATE INDEX IF NOT EXISTS idx_council_personas_council_id ON council_personas(council_id);
            """
        )
        _migrate_posts(conn)
        _migrate_personas(conn)
        _seed_defaults(conn)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _migrate_posts(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "posts")
    additions = {
        "council_id": "TEXT NOT NULL DEFAULT 'friend'",
        "discussion_summary": "TEXT NOT NULL DEFAULT ''",
        "model": "TEXT NOT NULL DEFAULT ''",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {name} {ddl}")


def _migrate_personas(conn: sqlite3.Connection) -> None:
    columns = _column_names(conn, "personas")
    additions = {
        "avatar_label": "TEXT NOT NULL DEFAULT ''",
        "role": "TEXT NOT NULL DEFAULT ''",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE personas ADD COLUMN {name} {ddl}")


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _seed_defaults(conn: sqlite3.Connection) -> None:
    for persona in DEFAULT_PERSONAS:
        conn.execute(
            """
            INSERT OR IGNORE INTO personas (
                id, name, avatar_label, personality, interests, speech_style, role, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                persona.id,
                persona.name,
                persona.avatar_label,
                persona.personality,
                persona.interests,
                persona.speech_style,
                persona.role,
                1 if persona.is_active else 0,
            ),
        )

    for council in DEFAULT_COUNCILS:
        conn.execute(
            """
            INSERT OR IGNORE INTO councils (id, name, description, simulation_style)
            VALUES (?, ?, ?, ?)
            """,
            (council.id, council.name, council.description, council.simulation_style),
        )
        for index, persona_id in enumerate(council.persona_ids):
            conn.execute(
                """
                INSERT OR IGNORE INTO council_personas (council_id, persona_id, position)
                VALUES (?, ?, ?)
                """,
                (council.id, persona_id, index),
            )
