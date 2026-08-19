"""SQLite persistence for the travel-booking demo: accounts, sessions,
saved trips, friends, and group trips.

SQLite, not the Postgres/Docker stack removed earlier this session --
same real-accounts-and-persistence outcome, appropriately scoped for a
local-only demo with no deployment. One file, no server process, no new
billing relationship, no docker-compose.

Every write goes through a single connection-per-call pattern
(`get_connection()`), which is fine at this scale (a local single-user
demo) -- no pooling, no migrations framework, just `CREATE TABLE IF NOT
EXISTS` run once at startup.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "travel.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS friendships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id INTEGER NOT NULL REFERENCES users(id),
    addressee_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted
    created_at REAL NOT NULL,
    UNIQUE(requester_id, addressee_id)
);

CREATE TABLE IF NOT EXISTS saved_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    hotel_json TEXT NOT NULL,
    flight_json TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    label TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    destination_code TEXT NOT NULL,
    join_code TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'collecting',  -- collecting | searched
    -- Which bandit arm the last search used. Persisted (not just held in
    -- memory) so the feedback/reward endpoint still works after a restart --
    -- otherwise the RL reward loop silently breaks and every 👍/👎 is lost.
    last_strategy TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_group_members (
    group_id INTEGER NOT NULL REFERENCES trip_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at REAL NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS trip_group_preferences (
    group_id INTEGER NOT NULL REFERENCES trip_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    preferences_json TEXT NOT NULL,
    submitted_at REAL NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS bandit_arm_stats (
    strategy TEXT PRIMARY KEY,
    times_chosen INTEGER NOT NULL DEFAULT 0,
    times_rewarded INTEGER NOT NULL DEFAULT 0
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive column migrations for databases created by an earlier version.

    `CREATE TABLE IF NOT EXISTS` silently does nothing when a table already
    exists, so a column added to SCHEMA later never lands on an existing local
    DB. Rather than telling people to delete their database (which would throw
    away their real accounts and saved trips), add missing columns in place.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(trip_groups)")}
    if existing and "last_strategy" not in existing:
        conn.execute("ALTER TABLE trip_groups ADD COLUMN last_strategy TEXT")


def purge_expired_sessions(conn: Optional[sqlite3.Connection] = None) -> int:
    """Delete sessions past their expiry. Without this the table grows forever;
    expired rows are already treated as logged-out, they were just never removed."""
    owned = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        conn.commit()
        return cur.rowcount
    finally:
        if owned:
            conn.close()


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
        purge_expired_sessions(conn)
    finally:
        conn.close()


def now() -> float:
    return time.time()
