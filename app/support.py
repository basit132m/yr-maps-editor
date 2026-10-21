"""Problem reports and feature requests.

Nobody has to make an account to send one. A visitor is identified by a
random token in a cookie, which is enough to show them their own history
and to rate-limit them, and they may leave an address if they want a
reply. When they happen to be signed in, that is recorded too, so the
admin can see who it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import db
from .config import REPORTS_PER_HOUR

KINDS = {"problem": "Problem report", "feature": "Feature request"}
STATUSES = {
    "open": "Open",
    "planned": "Planned",
    "done": "Done",
    "declined": "Not planned",
}

MAX_SUBJECT = 120
MAX_BODY = 4000
MAX_CONTACT = 160


class SupportError(ValueError):
    """Something the visitor can read and act on."""


@dataclass(frozen=True)
class Report:
    id: int
    kind: str
    subject: str
    body: str
    contact: str
    status: str
    admin_note: str
    created_at: str
    user_email: str | None

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, self.kind)

    @property
    def status_label(self) -> str:
        return STATUSES.get(self.status, self.status)


def _row_to_report(row) -> Report:
    return Report(
        id=row["id"], kind=row["kind"], subject=row["subject"], body=row["body"],
        contact=row["contact"], status=row["status"], admin_note=row["admin_note"],
        created_at=row["created_at"],
        user_email=row["user_email"] if "user_email" in row.keys() else None,
    )


def _clean(value: str, limit: int) -> str:
    return (value or "").strip()[:limit]


def submit(kind: str, subject: str, body: str, contact: str,
           client_token: str, user_id: int | None = None) -> Report:
    if kind not in KINDS:
        raise SupportError("Choose whether this is a problem or a feature request.")

    subject = _clean(subject, MAX_SUBJECT)
    body = _clean(body, MAX_BODY)
    contact = _clean(contact, MAX_CONTACT)

    if len(subject) < 3:
        raise SupportError("Give it a short title so we know what it is about.")
    if len(body) < 10:
        raise SupportError("Tell us a little more so we can act on it.")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with db.transaction() as conn:
        recent = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE client_token = ? AND created_at > ?",
            (client_token, cutoff),
        ).fetchone()[0]
        if recent >= REPORTS_PER_HOUR:
            raise SupportError(
                "You have sent several already. Please wait a while before "
                "sending another."
            )
        cursor = conn.execute(
            "INSERT INTO reports (kind, subject, body, contact, client_token,"
            " user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, subject, body, contact, client_token, user_id, db.now(), db.now()),
        )
        row = conn.execute("SELECT * FROM reports WHERE id = ?",
                           (cursor.lastrowid,)).fetchone()
    return _row_to_report(row)


def for_visitor(client_token: str, limit: int = 20) -> list[Report]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE client_token = ?"
            " ORDER BY id DESC LIMIT ?", (client_token, limit),
        ).fetchall()
    return [_row_to_report(row) for row in rows]


def listing(status: str | None = None, kind: str | None = None,
            limit: int = 100) -> list[Report]:
    sql = ("SELECT reports.*, users.email_display AS user_email FROM reports"
           " LEFT JOIN users ON users.id = reports.user_id WHERE 1 = 1")
    params: list = []
    if status in STATUSES:
        sql += " AND reports.status = ?"
        params.append(status)
    if kind in KINDS:
        sql += " AND reports.kind = ?"
        params.append(kind)
    sql += " ORDER BY reports.id DESC LIMIT ?"
    params.append(limit)

    with db.transaction() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_report(row) for row in rows]


def update(report_id: int, status: str, admin_note: str) -> None:
    if status not in STATUSES:
        raise SupportError("That is not a status we use.")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE reports SET status = ?, admin_note = ?, updated_at = ?"
            " WHERE id = ?",
            (status, _clean(admin_note, MAX_BODY), db.now(), report_id),
        )


def counts() -> dict[str, int]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM reports GROUP BY status").fetchall()
    tally = {status: 0 for status in STATUSES}
    tally.update({row["status"]: row["n"] for row in rows})
    tally["total"] = sum(row["n"] for row in rows)
    return tally
