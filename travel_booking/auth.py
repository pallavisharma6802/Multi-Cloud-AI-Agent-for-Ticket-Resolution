"""Password hashing + session management for the travel-booking demo.

Real hashing (salted PBKDF2-HMAC-SHA256, 100k iterations -- OWASP's
current minimum), not a weakened stand-in, even though this only ever
runs locally. Sessions are random opaque tokens in the `sessions` table,
set as an httponly cookie; no CSRF protection since this is a local
single-user demo, not a public deployment.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from travel_booking.db import get_connection, now

SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days
PBKDF2_ITERATIONS = 100_000


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return secrets.compare_digest(candidate, password_hash)


def create_user(username: str, password: str, display_name: str) -> dict:
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise ValueError(f"username '{username}' is already taken")
        password_hash, salt = hash_password(password)
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, password_salt, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, salt, display_name, now()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "username": username, "display_name": display_name}
    finally:
        conn.close()


def authenticate(username: str, password: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return None
        if not verify_password(password, row["password_hash"], row["password_salt"]):
            return None
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}
    finally:
        conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = get_connection()
    try:
        t = now()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, t, t + SESSION_TTL_SECONDS),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_user_from_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT u.id, u.username, u.display_name, s.expires_at
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token = ?""",
            (token,),
        ).fetchone()
        if row is None or row["expires_at"] < now():
            return None
        return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}
    finally:
        conn.close()


def delete_session(token: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()
