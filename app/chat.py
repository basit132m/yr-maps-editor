"""Live chat between a visitor and the admin.

No account required: a visitor's browser token is their thread. Messages
are delivered by polling rather than a websocket — the volume here is a
handful of conversations, polling survives every proxy and needs no
reconnection logic, and a stale connection cannot silently swallow a
message.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import db
from .config import CHAT_MESSAGES_PER_MINUTE

MAX_MESSAGE = 2000
VISITOR, ADMIN = "visitor", "admin"


class ChatError(ValueError):
    """Something the sender can read and act on."""


@dataclass(frozen=True)
class Message:
    id: int
    sender: str
    body: str
    created_at: str

    @property
    def from_admin(self) -> bool:
        return self.sender == ADMIN


@dataclass(frozen=True)
class Conversation:
    id: int
    client_token: str
    user_email: str | None
    created_at: str
    last_message_at: str
    admin_unread: int
    closed: bool
    preview: str = ""

    @property
    def who(self) -> str:
        if self.user_email:
            return self.user_email
        return f"Visitor {self.client_token[:6]}"


def _row_to_message(row) -> Message:
    return Message(id=row["id"], sender=row["sender"], body=row["body"],
                   created_at=row["created_at"])


def _row_to_conversation(row) -> Conversation:
    keys = row.keys()
    return Conversation(
        id=row["id"], client_token=row["client_token"],
        user_email=row["user_email"] if "user_email" in keys else None,
        created_at=row["created_at"], last_message_at=row["last_message_at"],
        admin_unread=row["admin_unread"], closed=bool(row["closed"]),
        preview=row["preview"] if "preview" in keys else "",
    )


def _conversation_id(conn, client_token: str, user_id: int | None,
                     create: bool) -> int | None:
    row = conn.execute("SELECT id FROM conversations WHERE client_token = ?",
                       (client_token,)).fetchone()
    if row is not None:
        if user_id is not None:
            conn.execute("UPDATE conversations SET user_id = ? WHERE id = ?",
                         (user_id, row["id"]))
        return row["id"]
    if not create:
        return None
    cursor = conn.execute(
        "INSERT INTO conversations (client_token, user_id, created_at,"
        " last_message_at) VALUES (?, ?, ?, ?)",
        (client_token, user_id, db.now(), db.now()),
    )
    return cursor.lastrowid


def send_from_visitor(client_token: str, body: str,
                      user_id: int | None = None) -> Message:
    body = (body or "").strip()[:MAX_MESSAGE]
    if not body:
        raise ChatError("Type a message first.")

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    with db.transaction() as conn:
        conversation = _conversation_id(conn, client_token, user_id, create=True)
        recent = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?"
            " AND sender = ? AND created_at > ?",
            (conversation, VISITOR, cutoff),
        ).fetchone()[0]
        if recent >= CHAT_MESSAGES_PER_MINUTE:
            raise ChatError("You are sending very quickly. Give it a moment.")

        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, sender, body, created_at)"
            " VALUES (?, ?, ?, ?)", (conversation, VISITOR, body, db.now()),
        )
        conn.execute(
            "UPDATE conversations SET last_message_at = ?,"
            " admin_unread = admin_unread + 1, closed = 0 WHERE id = ?",
            (db.now(), conversation),
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    return _row_to_message(row)


def send_from_admin(conversation_id: int, body: str) -> Message:
    body = (body or "").strip()[:MAX_MESSAGE]
    if not body:
        raise ChatError("Type a message first.")
    with db.transaction() as conn:
        exists = conn.execute("SELECT 1 FROM conversations WHERE id = ?",
                              (conversation_id,)).fetchone()
        if exists is None:
            raise ChatError("That conversation no longer exists.")
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, sender, body, created_at)"
            " VALUES (?, ?, ?, ?)", (conversation_id, ADMIN, body, db.now()),
        )
        conn.execute("UPDATE conversations SET last_message_at = ? WHERE id = ?",
                     (db.now(), conversation_id))
        row = conn.execute("SELECT * FROM messages WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    return _row_to_message(row)


def history(client_token: str, after_id: int = 0, limit: int = 100) -> list[Message]:
    """Messages in this visitor's thread newer than ``after_id``."""
    with db.transaction() as conn:
        conversation = _conversation_id(conn, client_token, None, create=False)
        if conversation is None:
            return []
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND id > ?"
            " ORDER BY id LIMIT ?", (conversation, after_id, limit),
        ).fetchall()
    return [_row_to_message(row) for row in rows]


def thread(conversation_id: int, after_id: int = 0, limit: int = 200) -> list[Message]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND id > ?"
            " ORDER BY id LIMIT ?", (conversation_id, after_id, limit),
        ).fetchall()
    return [_row_to_message(row) for row in rows]


def mark_read(conversation_id: int) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE conversations SET admin_unread = 0 WHERE id = ?",
                     (conversation_id,))


def set_closed(conversation_id: int, closed: bool) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE conversations SET closed = ? WHERE id = ?",
                     (1 if closed else 0, conversation_id))


def conversations(limit: int = 100) -> list[Conversation]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT c.*, users.email_display AS user_email,"
            "       (SELECT body FROM messages m WHERE m.conversation_id = c.id"
            "        ORDER BY m.id DESC LIMIT 1) AS preview"
            " FROM conversations c"
            " LEFT JOIN users ON users.id = c.user_id"
            " ORDER BY c.last_message_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [_row_to_conversation(row) for row in rows]


def get(conversation_id: int) -> Conversation | None:
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT c.*, users.email_display AS user_email FROM conversations c"
            " LEFT JOIN users ON users.id = c.user_id WHERE c.id = ?",
            (conversation_id,),
        ).fetchone()
    return _row_to_conversation(row) if row else None


def waiting_count() -> int:
    with db.transaction() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE admin_unread > 0").fetchone()[0]
