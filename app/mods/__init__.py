"""Registry of available map upgrades."""

from __future__ import annotations

from .auto_repair import AutoRepairMod
from .base import Change, Choice, Mod, Option
from .game_speed import GameSpeedMod
from .money import MoneyMod

#: Order here is the order shown in the web form.
REGISTRY: tuple[Mod, ...] = (
    AutoRepairMod(),
    MoneyMod(),
    GameSpeedMod(),
)

BY_ID = {mod.id: mod for mod in REGISTRY}

__all__ = ["REGISTRY", "BY_ID", "Mod", "Option", "Choice", "Change"]
