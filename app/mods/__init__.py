"""Registry of available map upgrades."""

from __future__ import annotations

from .auto_repair import AutoRepairMod
from .base import Change, Choice, Mod, Option
from .crates import CratesMod
from .game_speed import GameSpeedMod
from .money import MoneyMod
from .never_destroyed import NeverDestroyedMod

#: Order here is the order shown in the web form.
REGISTRY: tuple[Mod, ...] = (
    AutoRepairMod(),
    MoneyMod(),
    GameSpeedMod(),
    CratesMod(),
    NeverDestroyedMod(),
)

BY_ID = {mod.id: mod for mod in REGISTRY}

__all__ = ["REGISTRY", "BY_ID", "Mod", "Option", "Choice", "Change"]
