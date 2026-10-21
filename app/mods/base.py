"""The contract every map upgrade implements.

Adding a new upgrade means writing one :class:`Mod` subclass and listing it
in :mod:`app.mods` — the web layer discovers options and renders the form
from the registry, so no UI changes are needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..mapfile import YRMap


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Option:
    """One control in the upgrade form."""

    id: str
    label: str
    kind: str = "bool"          # "bool" or "choice"
    default: str = ""
    choices: tuple[Choice, ...] = ()
    help: str = ""


@dataclass
class Change:
    """A single key written into the map, for the result report."""

    section: str
    key: str
    value: str
    note: str = ""


class Mod:
    """Base class for upgrades. Subclasses override the class attributes.

    Deliberately not a dataclass: a generated ``__init__`` would reset these
    attributes to the base defaults on every subclass instance.
    """

    id: str = ""
    name: str = ""
    summary: str = ""
    #: Shown as a warning in the UI when the upgrade needs in-game checking.
    caveat: str = ""
    options: tuple[Option, ...] = ()

    def apply(self, ymap: "YRMap", values: dict[str, str]) -> list[Change]:
        raise NotImplementedError

    # -- helpers for subclasses -------------------------------------------

    @staticmethod
    def enabled(values: dict[str, str], option_id: str) -> bool:
        return str(values.get(option_id, "")).lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def write(ymap: "YRMap", changes: list[Change], section: str, key: str,
              value: str, note: str = "") -> None:
        ymap.ini.set(section, key, value)
        changes.append(Change(section=section, key=key, value=value, note=note))
