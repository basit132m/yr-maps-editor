"""More power-up crates.

``[CrateRules]`` holds the two numbers that matter, and the stock values
come from a community map that ships a full rules dump:

* ``CrateMinimum`` is 1. The engine normally keeps one crate per human
  player and never fewer than this, so on an eight-player map the default
  is about eight. Raising it is what puts more crates on the ground, and
  it only bites above the player count — setting it to 4 changes nothing
  on a six-player map.
* ``CrateRegen`` is 3: the average minutes before a collected crate comes
  back. Lowering it is what keeps them coming.
* ``CrateMaximum`` is 255 and is left alone; every amount here sits well
  under it.

A real community map ships ``CrateMinimum=15`` without trouble, so these
amounts are in proven territory.

On CnCNet the client has its own crate switch, which would otherwise cap
what the map asks for, so it is set to match rather than left to fight it.
"""

from __future__ import annotations

from .base import Change, Choice, Mod, Option

#: label -> (CrateRules CrateMinimum, CnCNet cmbCratesModifier)
#: The CnCNet modifier is kept in step with the amount: its lowest setting
#: caps the map at a single crate, which would undo the whole upgrade.
AMOUNTS = {
    "more":       ("10", "2"),
    "lots":       ("25", "3"),
    "everywhere": ("60", "3"),
}

AMOUNT_CHOICES = (
    Choice("lots", "Lots — about 25 crates on the map"),
    Choice("more", "More — about 10 crates on the map"),
    Choice("everywhere", "Everywhere — about 60 crates on the map"),
)

#: Average minutes before a collected crate reappears. Stock is 3.
FAST_REGEN = "1"

#: The engine's own ceiling, which no amount above may exceed.
CRATE_MAXIMUM = 255


class CratesMod(Mod):
    id = "crates"
    name = "More crates"
    summary = "Far more power-up crates on the map, and they come back sooner."
    caveat = (
        "Crates are luck, so more of them makes a match swingier. What they "
        "contain is unchanged: money, veterancy, armour and the rest, in "
        "the usual proportions."
    )
    options = (
        Option(
            id="amount",
            label="How many crates",
            kind="choice",
            default="lots",
            choices=AMOUNT_CHOICES,
            help=(
                "The game normally keeps about one crate per player, so "
                "anything here is a large increase."
            ),
        ),
        Option(
            id="regen",
            label="Crates come back sooner after being collected",
            kind="bool",
            default="1",
            help="About once a minute instead of once every three.",
        ),
        Option(
            id="forced",
            label="Match the CnCNet crate setting to this",
            kind="bool",
            default="1",
            help=(
                "Turns crates on and raises the client's own crate setting, "
                "which would otherwise cap what the map asks for."
            ),
            cncnet_only=True,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        amount = str(values.get("amount", "lots")).strip().lower()
        if amount not in AMOUNTS:
            amount = "lots"
        minimum, modifier = AMOUNTS[amount]
        label = next(c.label for c in AMOUNT_CHOICES if c.value == amount)

        self.write(ymap, changes, "CrateRules", "CrateMinimum", minimum,
                   note=label)

        if self.enabled(values, "regen"):
            self.write(ymap, changes, "CrateRules", "CrateRegen", FAST_REGEN,
                       note="A crate returns about once a minute")

        if self.enabled(values, "forced"):
            self.write(ymap, changes, "ForcedOptions", "chkCrates", "true",
                       note="Crates switched on")
            self.write(ymap, changes, "ForcedOptions", "cmbCratesModifier",
                       modifier, note="CnCNet crate setting raised to match")

        return changes
