"""Runtime settings, all overridable by environment variable."""

from __future__ import annotations

import os
from pathlib import Path

#: Where uploads wait between the analyse step and the apply step.
WORK_DIR = Path(os.getenv("YRME_WORK_DIR", "/tmp/yrme-uploads"))

#: How long an uploaded map stays on disk before the sweeper deletes it.
UPLOAD_TTL_SECONDS = int(os.getenv("YRME_UPLOAD_TTL", "1800"))

SITE_NAME = os.getenv("YRME_SITE_NAME", "YR Maps Editor")
