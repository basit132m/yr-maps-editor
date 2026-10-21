"""Runtime settings, all overridable by environment variable."""

from __future__ import annotations

import os
from pathlib import Path

#: Everything this app writes lives under here, on the mounted volume.
WORK_DIR = Path(os.getenv("YRME_WORK_DIR", "/tmp/yrme-data"))

#: Uploads get their own folder: the sweeper deletes anything old in it,
#: and the database must not be in its path.
UPLOAD_DIR = WORK_DIR / "uploads"

DB_PATH = Path(os.getenv("YRME_DB_PATH", str(WORK_DIR / "yrme.db")))

#: How long an uploaded map stays on disk before the sweeper deletes it.
UPLOAD_TTL_SECONDS = int(os.getenv("YRME_UPLOAD_TTL", "1800"))

SITE_NAME = os.getenv("YRME_SITE_NAME", "YR Maps Editor")

#: Only this domain may register. Gmail is what the audience uses, and
#: limiting it keeps throwaway addresses out of the support queue.
ALLOWED_EMAIL_DOMAINS = ("gmail.com", "googlemail.com")

#: Require an account before a map can be edited. Off by default: the tool
#: works in half a minute without one, and a forced signup costs far more
#: visitors than it gains. Flip it once the account features are worth it.
REQUIRE_LOGIN = os.getenv("YRME_REQUIRE_LOGIN", "0").lower() in {"1", "true", "yes"}

SESSION_COOKIE = "yrme_session"

#: Identifies a visitor who has not signed in, so their own reports and
#: chat thread come back to them. Random, and tied to nothing else.
CLIENT_COOKIE = "yrme_client"

#: Canonical Gmail addresses granted admin on sign-in, comma separated.
#: This is how the first admin is made without a console step.
ADMIN_EMAILS = tuple(
    part.strip().lower()
    for part in os.getenv("YRME_ADMIN_EMAILS", "").split(",")
    if part.strip()
)

#: Anti-spam: how many reports one visitor may send per hour.
REPORTS_PER_HOUR = int(os.getenv("YRME_REPORTS_PER_HOUR", "5"))

#: Anti-spam: how many chat messages one visitor may send per minute.
CHAT_MESSAGES_PER_MINUTE = int(os.getenv("YRME_CHAT_PER_MINUTE", "20"))

#: How long a signed-in session lasts without being used.
SESSION_DAYS = int(os.getenv("YRME_SESSION_DAYS", "30"))
