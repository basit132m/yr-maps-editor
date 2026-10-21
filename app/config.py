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

#: How long a signed-in session lasts without being used.
SESSION_DAYS = int(os.getenv("YRME_SESSION_DAYS", "30"))
