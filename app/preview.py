"""The minimap image embedded in a map file.

Every map carries its own preview: ``[Preview]`` gives the dimensions and
``[PreviewPack]`` holds the pixels, base64-encoded over numbered lines and
compressed with LZO1X, the same scheme ``IsoMapPack5`` uses. Nothing from the
game's own data files is needed to read it, so the preview can be shown
without shipping or licensing any game assets.

The payload is a sequence of chunks, each introduced by two 16-bit sizes —
the compressed length and the length once expanded — exactly as
``IsoMapPack5`` and ``OverlayPack`` are stored. Expanded, it is three bytes
per pixel.

Everything here reads attacker-supplied bytes, so every loop is bounded and
every malformed stream returns ``None`` rather than raising.
"""

from __future__ import annotations

import base64
import struct
import zlib

#: Refuse absurd dimensions before allocating anything for them. Real
#: previews in the wild run to roughly 330x200.
MAX_DIMENSION = 1024
MAX_PIXELS = 512 * 512


def _lzo1x_decompress(src: bytes, max_out: int) -> bytearray | None:
    """Expand one LZO1X stream.

    A direct transcription of the reference ``lzo1x_decompress``, whose
    control flow is a set of gotos; the ``label`` variable stands in for
    them so the structure stays recognisable against the original. Every
    read is bounds-checked because the input is attacker-supplied.
    """
    out = bytearray()
    ip = 0
    n = len(src)
    t = 0
    label = "start"

    def long_length(base: int, start: int) -> tuple[int, int] | None:
        """A zero length byte means 255 more per following zero byte."""
        total, i = 0, start
        while i < n and src[i] == 0:
            total += 255
            i += 1
        if i >= n:
            return None
        return total + base + src[i], i + 1

    while True:
        if len(out) > max_out:
            return None

        if label == "start":
            if ip >= n:
                return None
            if src[ip] > 17:
                t = src[ip] - 17
                ip += 1
                if t < 4:
                    label = "match_next"
                    continue
                out += src[ip:ip + t]
                ip += t
                label = "first_literal_run"
                continue
            label = "loop"

        if label == "loop":
            if ip >= n:
                return out
            t = src[ip]
            ip += 1
            if t >= 16:
                label = "match"
            else:
                if t == 0:
                    got = long_length(15, ip)
                    if got is None:
                        return None
                    t, ip = got
                t += 3
                if ip + t > n:
                    return None
                out += src[ip:ip + t]
                ip += t
                label = "first_literal_run"

        if label == "first_literal_run":
            if ip >= n:
                return out
            t = src[ip]
            ip += 1
            if t >= 16:
                label = "match"
            else:
                if ip >= n:
                    return None
                pos = len(out) - (1 + 0x0800) - (t >> 2) - (src[ip] << 2)
                ip += 1
                if pos < 0:
                    return None
                for k in range(3):
                    out.append(out[pos + k])
                label = "match_done"

        if label == "match":
            if t >= 64:
                if ip >= n:
                    return None
                pos = len(out) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
                ip += 1
                t = (t >> 5) - 1
            elif t >= 32:
                t &= 31
                if t == 0:
                    got = long_length(31, ip)
                    if got is None:
                        return None
                    t, ip = got
                if ip + 2 > n:
                    return None
                pos = len(out) - 1 - ((src[ip] >> 2) + (src[ip + 1] << 6))
                ip += 2
            elif t >= 16:
                base = len(out) - ((t & 8) << 11)
                t &= 7
                if t == 0:
                    got = long_length(7, ip)
                    if got is None:
                        return None
                    t, ip = got
                if ip + 2 > n:
                    return None
                pos = base - ((src[ip] >> 2) + (src[ip + 1] << 6))
                ip += 2
                if pos == len(out):
                    return out                      # end of stream marker
                pos -= 0x4000
            else:
                if ip >= n:
                    return None
                pos = len(out) - 1 - (t >> 2) - (src[ip] << 2)
                ip += 1
                if pos < 0 or pos + 2 > len(out):
                    return None
                out.append(out[pos])
                out.append(out[pos + 1])
                label = "match_done"
                continue

            if pos < 0:
                return None
            for k in range(t + 2):
                if pos + k >= len(out):
                    return None
                out.append(out[pos + k])
            label = "match_done"

        if label == "match_done":
            if ip < 2:
                return None
            t = src[ip - 2] & 3
            if t == 0:
                label = "loop"
                continue
            label = "match_next"

        if label == "match_next":
            if ip + t > n:
                return None
            out += src[ip:ip + t]
            ip += t
            if ip >= n:
                return out
            t = src[ip]
            ip += 1
            label = "match"


def _unpack_chunks(data: bytes, max_out: int) -> bytearray | None:
    """Expand the chunk sequence: [compressed size][output size][payload]."""
    out = bytearray()
    i = 0
    while i + 4 <= len(data) and len(out) < max_out:
        packed, unpacked = struct.unpack_from("<HH", data, i)
        i += 4
        if packed == 0 or i + packed > len(data):
            break
        piece = _lzo1x_decompress(data[i:i + packed], unpacked or max_out)
        if piece is None:
            return None
        out += piece
        i += packed
    return out


def _png(width: int, height: int, rgb: bytes) -> bytes:
    """Encode raw RGB as a PNG, so no imaging library is needed."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)                       # filter type 0 for every scanline
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def render_png(ini) -> bytes | None:
    """The map's own preview as a PNG, or None if it has none we can read."""
    size = ini.get("Preview", "Size")
    if not size:
        return None
    parts = [p.strip() for p in size.split(",")]
    if len(parts) < 4:
        return None
    try:
        width, height = int(parts[2]), int(parts[3])
    except ValueError:
        return None
    if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        return None
    if width * height > MAX_PIXELS:
        return None

    packed = "".join(value for _, value in ini.items("PreviewPack"))
    if not packed:
        return None
    try:
        payload = base64.b64decode(packed, validate=False)
    except Exception:
        return None

    needed = width * height * 3
    pixels = _unpack_chunks(payload, needed)
    if pixels is None or len(pixels) < needed:
        return None

    return _png(width, height, bytes(pixels[:needed]))
