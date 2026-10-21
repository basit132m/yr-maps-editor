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
        "fast_repair": "1", "auto": "1",
        "income": "1",
        "rate": "generous",
        "starting": "1",
        "credits": "0",
        "speed": "fastest",
        "build_speed": "fast", "strength": "unbreakable",
        "lock": "1",
    }


@pytest.fixture
def modded_map_bytes(map_bytes) -> bytes:
    """A map that already carries rules overrides, as real maps do.

    Modelled on community maps that ship their own [General], tuned
    buildings and an existing BuildSpeed, so upgrades must merge into
    them rather than replace them.
    """
    return map_bytes + (
        "\r\n[General]\r\n"
        "BuildSpeed=0.7\r\n"
        "GrowthRate=1\r\n"
        "RepairPercent=0%\r\n"
        "\r\n[GACNST]\r\n"
        "Strength=1000\r\n"
        "\r\n[GAGATE_A]\r\n"
        "Strength=1000\r\n"
        "\r\n[CAOILD]\r\n"
        "ProduceCashAmount=100\r\n"
        "ProduceCashDelay=100\r\n"
    ).encode("latin-1")


@pytest.fixture
def real_preview_map(map_bytes) -> bytes:
    """A map whose [PreviewPack] really decodes.

    Built here rather than shipped: a tiny image is compressed with the
    one LZO1X construct the decoder needs for it -- a literal run -- and
    framed in the chunk header the game uses.
    """
    import base64
    import struct

    width, height = 4, 2
    pixels = bytes([0x20, 0x40, 0x80] * (width * height))

    # At the start of an LZO1X stream a token above 17 means (token - 17)
    # literal bytes; 0x11 0x00 0x00 is the end-of-stream marker.
    body = bytes([len(pixels) + 17]) + pixels + b"\x11\x00\x00"
    chunk = struct.pack("<HH", len(body), len(pixels)) + body
    packed = base64.b64encode(chunk).decode()

    lines = "\r\n".join(
        f"{i + 1}={packed[i * 70:(i + 1) * 70]}"
        for i in range((len(packed) + 69) // 70)
    )
    return map_bytes + (
        f"\r\n[Preview]\r\nSize=0,0,{width},{height}\r\n"
        f"\r\n[PreviewPack]\r\n{lines}\r\n"
    ).encode("latin-1")
