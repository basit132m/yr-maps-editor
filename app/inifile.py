"""Byte-faithful INI reader/writer for Command & Conquer map files.

Westwood's map files (.map/.mpr/.yrm) are INI documents, but they violate
nearly every assumption a general-purpose INI parser makes:

* Sections such as ``[IsoMapPack5]`` hold base64 payloads split across
  hundreds of numerically-keyed lines; reordering or reflowing them
  corrupts the map's terrain.
* Duplicate keys appear in the wild and the engine keeps the first one.
* Line endings are CRLF, and a stray LF can upset older tooling.
* Values may contain ``=`` and non-UTF-8 bytes (Windows-1252 map names).

So this module never "re-serialises" a document. It keeps the original
lines verbatim and splices only the lines an edit actually touches. A
parse/serialise round-trip with no edits is guaranteed byte-identical,
which is the property every feature in this tool is built on.

Bytes are carried through ``latin-1``, which maps bytes 0x00-0xFF to the
same code points one-for-one, so decoding and re-encoding is lossless for
any input whatsoever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CODEC = "latin-1"

_SECTION_RE = re.compile(r"^\s*\[([^\]]*)\]")


def _split_eol(line: str) -> tuple[str, str]:
    """Split a line into its content and its line ending."""
    for eol in ("\r\n", "\n", "\r"):
        if line.endswith(eol):
            return line[: -len(eol)], eol
    return line, ""


def _is_comment(content: str) -> bool:
    stripped = content.lstrip()
    return stripped.startswith(";") or stripped.startswith("#")


@dataclass
class Section:
    """Where a section lives in the line list.

    ``header`` is the index of the ``[Name]`` line; ``end`` is one past the
    last line belonging to the section, i.e. the index of the next header
    (or the end of the file).
    """

    name: str
    header: int
    end: int

    @property
    def body(self) -> range:
        return range(self.header + 1, self.end)


@dataclass
class IniFile:
    lines: list[str] = field(default_factory=list)
    _sections: dict[str, Section] = field(default_factory=dict, repr=False)

    # ---------------------------------------------------------------- load

    @classmethod
    def from_bytes(cls, data: bytes) -> "IniFile":
        text = data.decode(CODEC)
        doc = cls(lines=text.splitlines(keepends=True))
        doc._reindex()
        return doc

    @classmethod
    def from_text(cls, text: str) -> "IniFile":
        return cls.from_bytes(text.encode(CODEC))

    def to_bytes(self) -> bytes:
        return "".join(self.lines).encode(CODEC)

    def to_text(self) -> str:
        return "".join(self.lines)

    # --------------------------------------------------------------- index

    def _reindex(self) -> None:
        """Rebuild the section map. Cheap enough to run after every edit."""
        self._sections = {}
        order: list[Section] = []
        for i, line in enumerate(self.lines):
            content, _ = _split_eol(line)
            if _is_comment(content):
                continue
            match = _SECTION_RE.match(content)
            if match:
                section = Section(name=match.group(1), header=i, end=len(self.lines))
                order.append(section)
        for prev, nxt in zip(order, order[1:]):
            prev.end = nxt.header
        for section in order:
            # The engine honours the first occurrence of a duplicated section.
            self._sections.setdefault(section.name.lower(), section)

    @property
    def dominant_eol(self) -> str:
        """The line ending to use for inserted lines.

        Map files are CRLF, so that is the fallback for a file whose
        existing lines give us nothing to copy.
        """
        counts = {"\r\n": 0, "\n": 0, "\r": 0}
        for line in self.lines:
            _, eol = _split_eol(line)
            if eol:
                counts[eol] += 1
        best = max(counts, key=lambda eol: counts[eol])
        return best if counts[best] else "\r\n"

    # --------------------------------------------------------------- query

    def sections(self) -> list[str]:
        return [section.name for section in self._sections.values()]

    def has_section(self, name: str) -> bool:
        return name.lower() in self._sections

    def _iter_entries(self, name: str):
        """Yield ``(line_index, key, value)`` for each key line in a section."""
        section = self._sections.get(name.lower())
        if section is None:
            return
        for i in section.body:
            content, _ = _split_eol(self.lines[i])
            if not content.strip() or _is_comment(content) or "=" not in content:
                continue
            key, _, value = content.partition("=")
            yield i, key.strip(), value

    def get(self, section: str, key: str, default: str | None = None) -> str | None:
        """First value for ``key``, with any trailing comment stripped."""
        for _, found, value in self._iter_entries(section):
            if found.lower() == key.lower():
                return value.split(";", 1)[0].strip()
        return default

    def get_int(self, section: str, key: str, default: int | None = None) -> int | None:
        raw = self.get(section, key)
        if raw is None:
            return default
        try:
            return int(raw.strip())
        except ValueError:
            return default

    def items(self, section: str) -> list[tuple[str, str]]:
        return [(k, v.split(";", 1)[0].strip()) for _, k, v in self._iter_entries(section)]

    def keys(self, section: str) -> list[str]:
        return [k for _, k, _ in self._iter_entries(section)]

    # --------------------------------------------------------------- mutate

    def set(self, section: str, key: str, value: str) -> bool:
        """Set ``key`` in ``section``, creating either if needed.

        Returns True when the file changed. Writing a value that is already
        present is a no-op, which keeps "apply the same mod twice" free of
        spurious diffs.
        """
        if not self.has_section(section):
            self.add_section(section)

        for i, found, existing in self._iter_entries(section):
            if found.lower() == key.lower():
                if existing.split(";", 1)[0].strip() == value:
                    return False
                _, eol = _split_eol(self.lines[i])
                self.lines[i] = f"{found}={value}{eol or self.dominant_eol}"
                return True

        self._append_to_section(section, f"{key}={value}")
        return True

    def unset(self, section: str, key: str) -> bool:
        """Remove every occurrence of ``key`` from ``section``."""
        targets = [i for i, found, _ in self._iter_entries(section) if found.lower() == key.lower()]
        if not targets:
            return False
        for i in reversed(targets):
            del self.lines[i]
        self._reindex()
        return True

    def add_section(self, name: str) -> None:
        """Append an empty section at the end of the document."""
        if self.has_section(name):
            return
        eol = self.dominant_eol
        if self.lines:
            last_content, last_eol = _split_eol(self.lines[-1])
            if not last_eol:
                self.lines[-1] = last_content + eol
            if last_content.strip():
                self.lines.append(eol)
        self.lines.append(f"[{name}]{eol}")
        self._reindex()

    def _append_to_section(self, name: str, content: str) -> None:
        section = self._sections[name.lower()]
        eol = self.dominant_eol

        # Insert after the section's last non-blank line so that blank
        # separator lines stay between sections where the author put them.
        insert_at = section.header + 1
        for i in section.body:
            line_content, _ = _split_eol(self.lines[i])
            if line_content.strip():
                insert_at = i + 1

        if insert_at - 1 < len(self.lines):
            prev_content, prev_eol = _split_eol(self.lines[insert_at - 1])
            if not prev_eol:
                self.lines[insert_at - 1] = prev_content + eol

        self.lines.insert(insert_at, f"{content}{eol}")
        self._reindex()
