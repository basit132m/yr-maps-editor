import base64
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fake_pack(lines: int, seed: int) -> str:
    """Base64 payload split across numbered lines, the way the game writes it."""
    rng = random.Random(seed)
    blob = base64.b64encode(bytes(rng.randrange(256) for _ in range(lines * 52))).decode()
    return "\r\n".join(f"{i + 1}={blob[i * 70:(i + 1) * 70]}" for i in range(lines))


@pytest.fixture
def map_bytes() -> bytes:
    """A map exercising the awkward parts: CRLF, comments, blank lines,
    duplicate keys, '=' inside values and big numbered base64 blocks."""
    return (
        "[Basic]\r\n"
        "Name=Tournament Island\r\n"
        "Author=Westwood\r\n"
        "; a comment the editor left behind\r\n"
        "MultiplayerOnly=yes\r\n"
        "Official=no\r\n"
        "Name=Duplicate Ignored\r\n"
        "\r\n"
        "[Map]\r\n"
        "Size=0,0,120,120\r\n"
        "LocalSize=2,4,116,112\r\n"
        "Theater=TEMPERATE\r\n"
        "\r\n"
        "[Waypoints]\r\n"
        "0=15420\r\n"
        "1=28311\r\n"
        "2=31002\r\n"
        "3=44120\r\n"
        "\r\n"
        "[SpecialFlags]\r\n"
        "DestroyableBridges=yes\r\n"
        "\r\n"
        "[Houses]\r\n"
        "0=Spain\r\n"
        "\r\n"
        "[Triggers]\r\n"
        "01000000=<none>,<none>,Example=Trigger,0,1,1,1,0\r\n"
        "\r\n"
        "[IsoMapPack5]\r\n" + _fake_pack(40, 1) + "\r\n"
        "\r\n"
        "[OverlayPack]\r\n" + _fake_pack(25, 2) + "\r\n"
        "\r\n"
        "[Digest]\r\n"
        "1=abcdefghijklmnop\r\n"
    ).encode("latin-1")


@pytest.fixture
def all_options() -> dict[str, str]:
    return {
        "forced_option": "1",
        "structures": "1",
        "credits": "0",
        "speed": "fastest",
        "lock": "1",
    }
