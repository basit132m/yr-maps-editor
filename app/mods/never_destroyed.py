"""Never-destroyed buildings.

Auto-repair on its own only starts the wrench; the building still takes
damage faster than it heals and can still fall. Making the repair itself
free and near-instant is what turns a base into something an attacker
cannot bring down, so it is kept separate and off by default.

Three global rules do it:

* ``RepairPercent`` — the cost of a full repair as a share of the
  building's price. Zero is free.
* ``RepairStep`` — health restored per repair step.
* ``RepairRate`` — minutes between steps. Retail is 0.016, roughly one
  step every 14 frames.

It also sets the ``[IQ]`` threshold itself, so the feature stands alone
whether or not auto-repair is also selected.
"""

from __future__ import annotations

from .auto_repair import REPAIR_SELL_IQ
from .base import Change, Choice, Mod, Option

#: strength -> (RepairRate, RepairStep, RepairPercent)
#: RepairStep stays modest on purpose: a value above a structure's own
#: Strength crashes the engine once that structure is damaged and repair
#: begins, and walls are the weakest buildings in the game. A community
#: map ships 35 without trouble, so these leave room.
STRENGTHS = {
    "tough": (".008", "15", "0%"),
    "very_tough": (".004", "20", "0%"),
    "unbreakable": (".002", "25", "0%"),
}

STRENGTH_CHOICES = (
    Choice("unbreakable", "Unbreakable — repairs faster than almost anything can damage it"),
    Choice("very_tough", "Very tough — heals quickly but can still be overwhelmed"),
    Choice("tough", "Tough — noticeably hard to kill"),
)


class NeverDestroyedMod(Mod):
    id = "never_destroyed"
    name = "Never-destroyed buildings"
    summary = (
        "Repairs are free and so fast that buildings heal damage about as "
        "quickly as it is dealt."
    )
    caveat = (
        "This is deliberately overpowered — a base with it switched on is "
        "very hard to lose. Leave it off for a fair match."
    )
    options = (
        Option(
            id="strength",
            label="How hard to kill",
            kind="choice",
            default="unbreakable",
            choices=STRENGTH_CHOICES,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        strength = str(values.get("strength", "unbreakable")).strip().lower()
        if strength not in STRENGTHS:
            strength = "unbreakable"
        rate, step, percent = STRENGTHS[strength]
        label = next(c.label for c in STRENGTH_CHOICES if c.value == strength)

        # Repair has to start by itself, or none of the rest is reached.
        self.write(ymap, changes, "IQ", "RepairSell", REPAIR_SELL_IQ,
                   note="Repair starts automatically")
        self.write(ymap, changes, "General", "RepairPercent", percent,
                   note="Repairing costs nothing")
        self.write(ymap, changes, "General", "RepairStep", step,
                   note=f"{step} health restored per step")
        self.write(ymap, changes, "General", "RepairRate", rate,
                   note=label)

        return changes
