"""SQLite storage for accounts and everything built on them.

SQLite is the right size here: one small VPS, one process, a userbase
measured in hundreds. It needs no separate service to run, back up or keep
patched, and the whole database is a single file on the mounted volume.

The schema is applied on every start. Each step is written so running it
again is harmless, which is all the migration this needs.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    email          TEXT    NOT NULL UNIQUE,   -- canonical form, for lookups
    email_display  TEXT    NOT NULL,          -- exactly as the user typed it
    name           TEXT    NOT NULL DEFAULT '',
    password_hash  TEXT    NOT NULL,
    is_admin       INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL,
    last_seen_at   TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    -- The cookie value is never stored, only its hash, so a copy of this
    -- file does not hand someone a working session.
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);

-- Problem reports and feature requests. No account is needed to send one:
-- a visitor is identified by a browser token, and may leave an address if
-- they want an answer.
CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY,
    kind         TEXT    NOT NULL,              -- 'problem' or 'feature'
    subject      TEXT    NOT NULL,
    body         TEXT    NOT NULL,
    contact      TEXT    NOT NULL DEFAULT '',   -- optional reply address
    client_token TEXT    NOT NULL,              -- anonymous visitor
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status       TEXT    NOT NULL DEFAULT 'open',
    admin_note   TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS reports_status ON reports(status, created_at);
CREATE INDEX IF NOT EXISTS reports_client ON reports(client_token);

-- One chat thread per visitor.
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY,
    client_token    TEXT    NOT NULL UNIQUE,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL,
    last_message_at TEXT    NOT NULL,
    admin_unread    INTEGER NOT NULL DEFAULT 0,
    closed          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS conversations_recent ON conversations(last_message_at);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender          TEXT    NOT NULL,           -- 'visitor' or 'admin'
    body            TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_thread ON messages(conversation_id, id);
"""


def now() -> str:
    """UTC timestamp, sortable as text so SQLite can compare it directly."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Readers do not block the writer, which matters once polling for chat.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)
