"""Accounts: who someone is, and how they prove it.

Registration is limited to Gmail. That brings a wrinkle worth handling
properly: Gmail ignores dots in the local part and everything after a
``+``, and ``googlemail.com`` is the same mailbox as ``gmail.com``. So
``John.Smith+yr@googlemail.com`` and ``johnsmith@gmail.com`` are one
person. Each address is reduced to a canonical form for lookups, while
the address as typed is kept for display and for writing to.

Passwords are stored with scrypt from the standard library, so there is
no password library to depend on or keep patched. Session cookies are
random tokens; only their hash reaches the database, so a copy of the
file does not hand anyone a working session.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import db
from .config import ALLOWED_EMAIL_DOMAINS, SESSION_DAYS

#: scrypt parameters. Roughly 100 ms per hash on a small VPS: slow enough
#: to make guessing expensive, fast enough that signing in feels instant.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200
MAX_NAME_LENGTH = 40

#: Gmail's own rule for the local part.
_GMAIL_LOCAL = re.compile(r"^[a-z0-9]([a-z0-9.]{4,28})[a-z0-9]$")


class AccountError(ValueError):
    """Something the person can read and act on."""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    email_display: str
    name: str
    is_admin: bool

    @property
    def display_name(self) -> str:
        return self.name or self.email_display.split("@")[0]

    @property
    def initials(self) -> str:
        source = (self.name or self.email_display).strip()
        parts = [p for p in re.split(r"[\s._-]+", source) if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return source[:2].upper() if source else "?"


# ----------------------------------------------------------------- email


def canonical_email(raw: str) -> str:
    """Reduce a Gmail address to the one mailbox it actually reaches.

    Raises :class:`AccountError` with a readable reason if it is not a
    Gmail address we can accept.
    """
    address = (raw or "").strip().lower()
    if not address or address.count("@") != 1:
        raise AccountError("Enter a valid email address.")

    local, domain = address.split("@")
    if domain not in ALLOWED_EMAIL_DOMAINS:
        raise AccountError("Only @gmail.com addresses can be used here.")

    local = local.split("+", 1)[0]          # +tag goes to the same inbox
    if not _GMAIL_LOCAL.match(local):
        raise AccountError("That does not look like a Gmail address.")

    local = local.replace(".", "")          # Gmail ignores dots
    if not local:
        raise AccountError("That does not look like a Gmail address.")

    return f"{local}@gmail.com"


# -------------------------------------------------------------- password


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                             n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                 n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected)


def check_password_quality(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(
            f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AccountError("That password is too long.")


# ----------------------------------------------------------------- users


def _row_to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], email=row["email"], email_display=row["email_display"],
                name=row["name"], is_admin=bool(row["is_admin"]))


def create_user(email: str, password: str, name: str = "") -> User:
    canonical = canonical_email(email)
    check_password_quality(password)
    display = (email or "").strip()
    name = (name or "").strip()[:MAX_NAME_LENGTH]

    with db.transaction() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, email_display, name, password_hash, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (canonical, display, name, hash_password(password), db.now()),
            )
        except sqlite3.IntegrityError:
            raise AccountError("An account already exists for that address.") from None
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    return _row_to_user(row)


def authenticate(email: str, password: str) -> User:
    try:
        canonical = canonical_email(email)
    except AccountError:
        # Never reveal which half was wrong.
        raise AccountError("That email and password do not match.") from None

    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (canonical,)).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        raise AccountError("That email and password do not match.")
    return _row_to_user(row)


def set_name(user_id: int, name: str) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?",
                     ((name or "").strip()[:MAX_NAME_LENGTH], user_id))


def change_password(user_id: int, current: str, new: str) -> None:
    with db.transaction() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?",
                           (user_id,)).fetchone()
        if row is None or not verify_password(current, row["password_hash"]):
            raise AccountError("Your current password is not correct.")
        check_password_quality(new)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(new), user_id))
        # Changing a password ends every other session.
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# -------------------------------------------------------------- sessions


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (_hash_token(token), user_id, db.now(),
             expires.isoformat(timespec="seconds")),
        )
    return token


def user_for_session(token: str | None) -> User | None:
    if not token:
        return None
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
            " WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
            (_hash_token(token), db.now()),
        ).fetchone()
        if row is not None:
            conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?",
                         (db.now(), row["id"]))
    return _row_to_user(row) if row else None


def end_session(token: str | None) -> None:
    if not token:
        return
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
