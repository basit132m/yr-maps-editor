"""Randomised round-trip checks.

Real maps are written by several generations of editors, so the parser
meets layouts no hand-written fixture anticipates. These cases shake out
the structural edge cases; `tools/verify_corpus.py` does the same against
a folder of genuine maps.
"""

import random
import string

import pytest

from app.inifile import IniFile, _split_eol

ALPHABET = string.ascii_letters + string.digits + " \t;=[]#.,-_/+"


def random_document(rng: random.Random) -> bytes:
    lines = []
    for _ in range(rng.randrange(1, 60)):
        roll = rng.random()
        if roll < 0.15:
            lines.append(f"[{''.join(rng.choices(ALPHABET, k=rng.randrange(0, 12)))}]")
        elif roll < 0.25:
            lines.append("")
        elif roll < 0.35:
            lines.append("; " + "".join(rng.choices(ALPHABET, k=rng.randrange(0, 30))))
        else:
            key = "".join(rng.choices(ALPHABET, k=rng.randrange(0, 10)))
            value = "".join(rng.choices(ALPHABET, k=rng.randrange(0, 40)))
            lines.append(f"{key}={value}")

    eol = rng.choice(["\r\n", "\n", "\r"])
    text = eol.join(lines)
    if rng.random() < 0.7:
        text += eol
    return text.encode("latin-1")


@pytest.mark.parametrize("seed", range(300))
def test_random_documents_roundtrip(seed):
    raw = random_document(random.Random(seed))
    assert IniFile.from_bytes(raw).to_bytes() == raw


@pytest.mark.parametrize("seed", range(100))
def test_edits_only_append(seed):
    """Adding a section must leave every original byte where it was.

    The one permitted difference is a terminator added to a final line that
    lacked one, since the new section cannot share that line.
    """
    rng = random.Random(10_000 + seed)
    raw = random_document(rng)
    doc = IniFile.from_bytes(raw)
    eol = doc.dominant_eol
    doc.set("ForcedOptions", "chkAutoRepair", "true")

    assert doc.get("ForcedOptions", "chkAutoRepair") == "true"

    output = doc.to_bytes()
    assert output.startswith(raw) or output.startswith(raw + eol.encode("latin-1"))

    # And the original line structure survives in order.
    def contents(lines):
        return [_split_eol(line)[0] for line in lines]

    remaining = iter(contents(doc.lines))
    for line in contents(IniFile.from_bytes(raw).lines):
        assert any(candidate == line for candidate in remaining), line


@pytest.mark.parametrize("seed", range(100))
def test_random_bytes_never_crash_the_parser(seed):
    rng = random.Random(20_000 + seed)
    raw = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 2000)))
    assert IniFile.from_bytes(raw).to_bytes() == raw
