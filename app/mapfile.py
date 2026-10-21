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

#: Light-post types from rulesmd.ini's [BuildingTypes]. Maps retint these
#: constantly to set a mood; it says nothing about how the map plays, so
#: they do not count towards calling a map a conversion.
LIGHTING_SECTIONS = frozenset({
    "galite", "redlamp", "grenlamp", "bluelamp", "yelwlamp", "purplamp",
    "inoranlamp", "ingrnlmp", "inredlmp", "inblulmp", "ingalite",
    "inyelwlamp", "inpurplamp", "neglamp", "negred", "tstlamp",
    "temmorlamp", "temdaylamp", "temduslamp", "temnitlamp",
    "snomorlamp", "snodaylamp", "snoduslamp", "snonitlamp",
})

#: Above this many gameplay overrides a map is not a plain map any more but
#: a conversion with its own balance. Drawn from a corpus of real maps,
#: where ordinary ones carry under ten and conversions carry forty to two
#: thousand.
HEAVILY_MODIFIED_THRESHOLD = 25


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
    has_preview: bool
    forced_options: list[tuple[str, str]] = field(default_factory=list)
    rules_overrides: list[str] = field(default_factory=list)
    #: (section, credits per payment) for buildings the map already pays from.
    existing_income: list[tuple[str, str]] = field(default_factory=list)
    size_bytes: int = 0
    section_count: int = 0

    @property
    def gameplay_overrides(self) -> list[str]:
        """Overrides that affect play, i.e. everything but lighting."""
        return [s for s in self.rules_overrides if s.lower() not in LIGHTING_SECTIONS]

    @property
    def heavily_modified(self) -> bool:
        return len(self.gameplay_overrides) >= HEAVILY_MODIFIED_THRESHOLD


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

    def has_preview(self) -> bool:
        """Whether the map carries a minimap image we could decode.

        Only checks that the pieces are present; decoding happens when the
        image is actually requested.
        """
        if not self.ini.has_section("PreviewPack"):
            return False
        size = self.ini.get("Preview", "Size") or ""
        parts = [p.strip() for p in size.split(",")]
        if len(parts) < 4:
            return False
        try:
            return int(parts[2]) > 0 and int(parts[3]) > 0
        except ValueError:
            return False

    def income_sources(self) -> list[tuple[str, str]]:
        """Buildings the map already pays its players from.

        Several community maps hand out credits through the engine's
        ProduceCash rules. Adding more income stacks on top of these, which
        is worth telling the user before they double a map's economy.
        """
        found = []
        for name in self.ini.sections():
            amount = self.ini.get(name, "ProduceCashAmount")
            if amount and amount.strip() not in {"", "0"}:
                found.append((name, amount.strip()))
        return found

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
            has_preview=self.has_preview(),
            forced_options=self.ini.items("ForcedOptions"),
            rules_overrides=self.rules_override_sections(),
            existing_income=self.income_sources(),
            size_bytes=len(self.ini.to_bytes()),
            section_count=len(self.ini.sections()),
        )

    # --------------------------------------------------------------- edits

    def set_display_name(self, name: str) -> bool:
        """Rename the map so players can tell a modified copy from the original."""
        return self.ini.set("Basic", "Name", name[:64])
