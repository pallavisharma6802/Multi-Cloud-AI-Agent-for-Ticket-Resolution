"""PostgreSQL persistence for the travel-booking app: accounts, sessions,
saved trips, friends, and group trips.

`_Connection` wraps psycopg2 to match sqlite3's `conn.execute(sql, params)`
interface (no separate cursor, `?` placeholders, dict-like rows,
`cursor.lastrowid`) so auth.py/api.py/preference_aggregator.py didn't need
touching for the driver swap. `?` gets translated to `%s`, rows come back
via RealDictCursor, and `.lastrowid` is faked with an automatic
`RETURNING id` on tables that have a surrogate `id` primary key.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

import psycopg2
import psycopg2.extras

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS friendships (
    id SERIAL PRIMARY KEY,
    requester_id INTEGER NOT NULL REFERENCES users(id),
    addressee_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted
    created_at DOUBLE PRECISION NOT NULL,
    UNIQUE(requester_id, addressee_id)
);

CREATE TABLE IF NOT EXISTS saved_trips (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    hotel_json TEXT NOT NULL,
    flight_json TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    label TEXT,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    destination_code TEXT NOT NULL,
    join_code TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'collecting',  -- collecting | searched
    -- Which bandit arm the last search used. Persisted (not just held in
    -- memory) so the feedback/reward endpoint still works after a restart --
    -- otherwise the RL reward loop silently breaks and every thumbs up/down is lost.
    last_strategy TEXT,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_group_members (
    group_id INTEGER NOT NULL REFERENCES trip_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS trip_group_preferences (
    group_id INTEGER NOT NULL REFERENCES trip_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    preferences_json TEXT NOT NULL,
    submitted_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS bandit_arm_stats (
    strategy TEXT PRIMARY KEY,
    times_chosen INTEGER NOT NULL DEFAULT 0,
    times_rewarded INTEGER NOT NULL DEFAULT 0
);
"""

# Tables with a surrogate `id` SERIAL primary key -- INSERTs into these get
# `RETURNING id` appended automatically so `.lastrowid` behaves like
# sqlite3's did. Every other table has a natural/composite key and must NOT
# get this appended (there's no `id` column to return).
_TABLES_WITH_ID = ("users", "friendships", "saved_trips", "trip_groups")
_INSERT_INTO_RE = re.compile(r"^\s*INSERT\s+INTO\s+(" + "|".join(_TABLES_WITH_ID) + r")\b", re.IGNORECASE)


class _Result:
    """Mimics the object sqlite3's `conn.execute(...)` returns."""

    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


class _Connection:
    """Wraps a psycopg2 connection so every existing `conn.execute(sql,
    params)` call site in this codebase keeps working unchanged against
    Postgres -- see module docstring."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql: str, params=()):
        pg_sql = sql.replace("?", "%s")
        add_returning = bool(_INSERT_INTO_RE.match(sql)) and "RETURNING" not in sql.upper()
        if add_returning:
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params)
        lastrowid = None
        if add_returning:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None
        return _Result(cur, lastrowid)

    def executescript(self, sql: str) -> None:
        cur = self._raw.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


def _database_url() -> str:
    url = os.environ.get("TRAVEL_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TRAVEL_DATABASE_URL is not set -- point it at a Postgres connection string "
            "(e.g. a free Neon.tech database) before starting the app. See .env.example."
        )
    return url


def get_connection() -> _Connection:
    raw = psycopg2.connect(_database_url())
    return _Connection(raw)


def _migrate(conn: _Connection) -> None:
    """Additive column migrations for databases created by an earlier
    version's schema -- so an existing deployed database (real accounts,
    real saved trips) never has to be dropped just to pick up a new column.
    """
    exists = conn.execute("SELECT to_regclass('public.trip_groups') IS NOT NULL AS tbl_exists").fetchone()
    if not exists or not exists["tbl_exists"]:
        return
    cols = {
        r["column_name"]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'trip_groups'"
        ).fetchall()
    }
    if "last_strategy" not in cols:
        conn.execute("ALTER TABLE trip_groups ADD COLUMN last_strategy TEXT")


def purge_expired_sessions(conn: Optional[_Connection] = None) -> int:
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
