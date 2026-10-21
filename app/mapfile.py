"""Loading, validating and describing a Red Alert 2 / Yuri's Revenge map."""

from __future__ import annotations

from dataclasses import dataclass, field

from .inifile import IniFile

#: ``.map`` is what the CnCNet client lists, ``.mpr`` is RA2's own extension
#: and ``.yrm`` is Yuri's Revenge's. All three hold the same INI document.
ALLOWED_EXTENSIONS = {".map", ".mpr", ".yrm"}

#: Generous enough for the largest community maps, small enough that a
#: malicious upload cannot exhaust the server's disk.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: Start locations live in [Waypoints] under keys 0-7.
START_WAYPOINTS = [str(n) for n in range(8)]


class MapError(ValueError):
    """The uploaded file is not a map this tool can safely edit."""


@dataclass
class MapInfo:
    name: str
    author: str
    theater: str
    width: int | None
    height: int | None
    players: int
    is_multiplayer: bool
    has_terrain_data: bool
    forced_options: list[tuple[str, str]] = field(default_factory=list)
    rules_overrides: list[str] = field(default_factory=list)
    size_bytes: int = 0
    section_count: int = 0


class YRMap:
    """A map file plus the queries and edits this tool needs.

    The underlying :class:`IniFile` is never rewritten wholesale, so the
    binary payload sections survive untouched.
    """

    #: Sections holding compressed binary payloads. We read none of them and
    #: write none of them; they are listed so the validator can confirm the
    #: upload really is a map and so edits can be checked against them.
    BINARY_SECTIONS = ("IsoMapPack5", "OverlayPack", "OverlayDataPack", "PreviewPack")

    def __init__(self, ini: IniFile, filename: str = "map.map"):
        self.ini = ini
        self.filename = filename

    # ---------------------------------------------------------------- load

    @classmethod
    def load(cls, data: bytes, filename: str = "map.map") -> "YRMap":
        if not data:
            raise MapError("The file is empty.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise MapError(
                f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB, "
                "which is bigger than any real map."
            )
        if b"\x00" in data[:4096]:
            raise MapError(
                "This looks like a binary file, not a map. If you have a .mmx or .yro "
                "map package, extract the .mpr/.yrm from it first with XCC Mixer."
            )

        ini = IniFile.from_bytes(data)
        instance = cls(ini, filename)
        instance._validate()
        return instance

    def _validate(self) -> None:
        if not self.ini.has_section("Map"):
            raise MapError(
                "No [Map] section found. This does not look like a Red Alert 2 or "
                "Yuri's Revenge map file."
            )
        if not self.ini.has_section("Basic"):
            raise MapError("No [Basic] section found. The map file looks incomplete.")

    def to_bytes(self) -> bytes:
        return self.ini.to_bytes()

    # ------------------------------------------------------------- queries

    def dimensions(self) -> tuple[int | None, int | None]:
        """Playable width and height from [Map] LocalSize, falling back to Size."""
        for key in ("LocalSize", "Size"):
            raw = self.ini.get("Map", key)
            if not raw:
                continue
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) >= 4:
                try:
                    return int(parts[2]), int(parts[3])
                except ValueError:
                    continue
        return None, None

    def player_count(self) -> int:
        return sum(1 for wp in START_WAYPOINTS if self.ini.get("Waypoints", wp))

    def is_multiplayer(self) -> bool:
        """Multiplayer maps are flagged in [Basic] and carry start locations."""
        flag = (self.ini.get("Basic", "MultiplayerOnly") or "").strip().lower()
        if flag in {"yes", "true", "1"}:
            return True
        return self.player_count() >= 2

    def rules_override_sections(self) -> list[str]:
        """Sections that look like rulesmd.ini overrides carried by the map.

        Anything that is neither a known structural section nor a binary
        payload is, in practice, a rules override.
        """
        known = {
            "basic", "map", "waypoints", "terrain", "celltags", "units", "infantry",
            "structures", "aircraft", "smudge", "overlay", "houses", "countries",
            "triggers", "events", "actions", "tags", "teamtypes", "taskforces",
            "scripts", "aitriggertypes", "aitriggerenables", "preview", "digest",
            "specialflags", "variablenames", "lighting", "header", "sounds",
            "forcedoptions", "globalvariables", "briefing", "multimaps", "tutorial",
            "header", "authorinformation", "scripttypes", "smudge", "special",
            "aircrafttypes", "infantrytypes", "vehicletypes", "buildingtypes",
            "fa2spversioncontrol", "aitriggertypesenable", "digest",
        }
        # FinalAlert writes a section per country, and one per team type /
        # script / task force keyed by its eight-digit ID. Neither is a
        # rules override.
        known.update({
            "africans", "alliance", "americans", "arabs", "british",
            "confederation", "french", "gdi", "germans", "neutral", "nod",
            "russians", "yuricountry", "special",
        })
        known.update(section.lower() for section in self.BINARY_SECTIONS)
        def is_id_section(name: str) -> bool:
            return len(name) == 8 and all(c in "0123456789ABCDEFabcdef" for c in name)

        return [
            name for name in self.ini.sections()
            if name.lower() not in known and not is_id_section(name)
        ]

    def info(self) -> MapInfo:
        width, height = self.dimensions()
        return MapInfo(
            name=self.ini.get("Basic", "Name") or "(unnamed)",
            author=self.ini.get("Basic", "Author") or "(unknown)",
            theater=self.ini.get("Map", "Theater") or "(unknown)",
            width=width,
            height=height,
            players=self.player_count(),
            is_multiplayer=self.is_multiplayer(),
            has_terrain_data=self.ini.has_section("IsoMapPack5"),
            forced_options=self.ini.items("ForcedOptions"),
            rules_overrides=self.rules_override_sections(),
            size_bytes=len(self.ini.to_bytes()),
            section_count=len(self.ini.sections()),
        )

    # --------------------------------------------------------------- edits

    def set_display_name(self, name: str) -> bool:
        """Rename the map so players can tell a modified copy from the original."""
        return self.ini.set("Basic", "Name", name[:64])
