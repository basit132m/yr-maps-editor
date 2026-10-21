#!/usr/bin/env python3
"""Grant or remove admin, straight in the database.

The environment variable is the usual route, but it has several ways to
quietly not arrive: the line missing from .env, the container not
recreated so it never reads it, or an address that does not reduce to the
same Gmail mailbox. None of those say anything useful on screen.

This does not depend on any of it. Run it inside the container:

    docker compose exec app python3 tools/make_admin.py you@gmail.com

With no arguments it lists the accounts and what the server has
configured, which is usually enough to see what went wrong.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import accounts, db  # noqa: E402


def report() -> int:
    configured = accounts.admin_emails()
    raw = os.getenv("YRME_ADMIN_EMAILS", "")

    print("YRME_ADMIN_EMAILS as the container sees it:")
    print(f"  {raw!r}" + ("   <-- EMPTY: the variable never reached the container"
                          if not raw.strip() else ""))
    if configured:
        print("  reduced to:", ", ".join(sorted(configured)))

    people = accounts.everyone()
    print(f"\nAccounts ({len(people)}):")
    if not people:
        print("  none yet - sign up at /signup first")
    for user in people:
        flag = "ADMIN" if user.is_admin else "     "
        print(f"  [{flag}] {user.email:38} typed as {user.email_display}")

    print("\nTo grant admin:")
    print("  python3 tools/make_admin.py <address>")
    return 0


def main() -> int:
    db.init()
    args = [a for a in sys.argv[1:] if a != "--remove"]
    if not args:
        return report()

    try:
        user = accounts.grant_admin(args[0], admin="--remove" not in sys.argv)
    except accounts.AccountError as exc:
        print(f"Could not do that: {exc}", file=sys.stderr)
        print("\nAccounts that do exist:", file=sys.stderr)
        for other in accounts.everyone():
            print(f"  {other.email}", file=sys.stderr)
        return 1

    state = "is now an administrator" if user.is_admin else "is no longer an administrator"
    print(f"{user.email} {state}.")
    print("Reload /admin - no sign-out needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
