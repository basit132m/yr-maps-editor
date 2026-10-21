#!/usr/bin/env python3
"""Validate the editor against a folder of real maps.

Synthetic fixtures only prove what we thought to imagine. Point this at a
directory of genuine maps and it checks three things on every one:

1. Parsing and re-serialising returns byte-identical output.
2. Applying every upgrade changes only the keys it should.
3. The result still loads as a map.

    python3 tools/verify_corpus.py ~/maps --recursive

Exit status is non-zero if any map fails, so it can gate a deployment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.inifile import IniFile  # noqa: E402
from app.mapfile import ALLOWED_EXTENSIONS, MapError, YRMap  # noqa: E402
from app.mods import REGISTRY  # noqa: E402
from app.mods.auto_repair import BUILDINGS  # noqa: E402
from app.mods.money import CONSTRUCTION_YARDS  # noqa: E402

ALL_OPTIONS = {
    "forced_option": "1", "structures": "1", "fast_repair": "1", "auto": "1",
    "income": "1", "rate": "generous", "starting": "1", "credits": "0",
    "speed": "fastest", "build_speed": "fast", "buildup": "1", "strength": "unbreakable", "lock": "1",
}

#: Sections an upgrade is allowed to create.
EXPECTED_NEW = {"ForcedOptions", "General", "IQ", *BUILDINGS, *CONSTRUCTION_YARDS}

#: Payload sections that must come out byte-for-byte as they went in.
PROTECTED = ("IsoMapPack5", "OverlayPack", "OverlayDataPack", "PreviewPack", "Digest")


def check(path: Path) -> list[str]:
    problems: list[str] = []
    raw = path.read_bytes()

    if IniFile.from_bytes(raw).to_bytes() != raw:
        problems.append("round-trip is not byte-identical")

    try:
        ymap = YRMap.load(raw, path.name)
    except MapError as exc:
        return problems + [f"will be rejected on upload: {exc}"]

    before = IniFile.from_bytes(raw)
    for mod in REGISTRY:
        mod.apply(ymap, ALL_OPTIONS)
    after = ymap.ini

    for section in PROTECTED:
        if before.items(section) != after.items(section):
            problems.append(f"[{section}] was modified")

    unexpected = (set(after.sections()) - set(before.sections())) - EXPECTED_NEW
    if unexpected:
        problems.append(f"unexpected new sections: {sorted(unexpected)}")

    for key, expected in (
        ("chkAutoRepair", "true"), ("cmbCredits", "0"),
        ("cmbGameSpeedCapSkirmish", "0"), ("chkDisableGameSpeed", "true"),
    ):
        if after.get("ForcedOptions", key) != expected:
            problems.append(f"ForcedOptions/{key} not written")

    try:
        YRMap.load(ymap.to_bytes(), path.name)
    except MapError as exc:
        problems.append(f"edited map no longer loads: {exc}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list every map, not just the failures")
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Not a directory: {args.directory}", file=sys.stderr)
        return 2

    pattern = "**/*" if args.recursive else "*"
    maps = sorted(
        p for p in args.directory.glob(pattern)
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
    )
    if not maps:
        print(f"No .map/.mpr/.yrm files found in {args.directory}", file=sys.stderr)
        return 2

    failed = 0
    for path in maps:
        try:
            problems = check(path)
        except Exception as exc:  # a crash is itself a failure worth reporting
            problems = [f"crashed: {type(exc).__name__}: {exc}"]
        if problems:
            failed += 1
            print(f"FAIL  {path.name}")
            for problem in problems:
                print(f"        - {problem}")
        elif args.verbose:
            print(f"ok    {path.name}")

    print(f"\n{len(maps) - failed}/{len(maps)} maps passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
